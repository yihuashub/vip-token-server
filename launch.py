"""Launcher for the VIP Token Server desktop shortcut.

Invoked when the user double-clicks the desktop icon. Behavior:

1. Health-check http://127.0.0.1:8080/health.
2. If responding: open the browser to the UI and exit.
3. If not responding: spawn uvicorn as a fully detached background process
   (no console window on Windows), wait up to ~15 seconds for it to be ready,
   then open the browser.

Designed to be invoked via `pythonw.exe` on Windows (no console window).
Cross-platform-friendly so the same script can be tested on macOS/Linux.
"""

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

URL = "http://127.0.0.1:8080"
HEALTH = URL + "/health"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(PROJECT_DIR, ".server.pid")

# Default data path: C:\vip-data\credentials.json on Windows, ./credentials.json elsewhere.
DEFAULT_DATA_PATH = (
    r"C:\vip-data\credentials.json"
    if sys.platform == "win32"
    else os.path.join(PROJECT_DIR, "credentials.json")
)
DATA_PATH = os.environ.get("DATA_PATH", DEFAULT_DATA_PATH)


def is_running() -> bool:
    try:
        with urllib.request.urlopen(HEALTH, timeout=0.6) as r:
            return r.status == 200
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return False


def venv_python() -> str:
    """Resolve the venv's pythonw/python executable, or fall back to system Python."""
    if sys.platform == "win32":
        candidate = os.path.join(PROJECT_DIR, "venv", "Scripts", "pythonw.exe")
    else:
        candidate = os.path.join(PROJECT_DIR, "venv", "bin", "python3")
    if os.path.exists(candidate):
        return candidate
    return "pythonw.exe" if sys.platform == "win32" else sys.executable


def start_server() -> bool:
    os.makedirs(os.path.dirname(DATA_PATH) or ".", exist_ok=True)

    env = {**os.environ, "DATA_PATH": DATA_PATH}
    cmd = [
        venv_python(),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8080",
        "--log-level",
        "warning",
    ]

    kwargs = dict(
        cwd=PROJECT_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    if sys.platform == "win32":
        # DETACHED_PROCESS + CREATE_NO_WINDOW: no console window, survives parent exit.
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NO_WINDOW
            | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        # POSIX: new session so it survives parent exit.
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **kwargs)

    try:
        with open(PID_FILE, "w") as f:
            f.write(str(proc.pid))
    except OSError:
        pass  # PID file is best-effort

    # Poll for readiness; uvicorn cold start is typically 1-3s.
    for _ in range(30):
        time.sleep(0.5)
        if is_running():
            return True
    return False


def error_dialog(msg: str) -> None:
    """Show a GUI error if we have no console (we were launched via pythonw)."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, msg, "VIP Token Server", 0x10)
            return
        except Exception:
            pass
    print(msg, file=sys.stderr)


def main() -> int:
    if not is_running():
        if not start_server():
            error_dialog(
                "Could not start the VIP Token Server within 15 seconds.\n\n"
                "Try running install.bat again, or run.bat to see error output."
            )
            return 1
    webbrowser.open(URL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
