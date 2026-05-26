# vip-token-server

A small FastAPI server that holds many Symantec VIP credentials and serves their current TOTP codes via a localhost web UI. Designed to be deployed on a single VM (typically Windows) and accessed by multiple users who RDP in.

## Why this exists

The official Symantec VIP Access desktop client binds each credential to a machine fingerprint. On a VM that gets snapshotted, reimaged, or has the client reinstalled, the credential ID **rotates** — forcing a painful re-bind on every target service (E\*TRADE, Schwab, Fidelity, Vanguard, AWS root, etc.) every single time.

This server side-steps the problem by:

1. **Provisioning credentials programmatically** with [python-vipaccess](https://github.com/dlenski/python-vipaccess) — so the credential ID and seed are owned by *you*, not the opaque desktop client.
2. **Storing the seeds in a plain JSON file** you control and back up.
3. **Computing TOTP codes locally** from those seeds with the standard RFC 6238 algorithm. No network call to Symantec is needed once the credential is provisioned.

Once a credential ID is in your JSON file, it is fixed for the credential's 3-year lifetime — and survives reboots, snapshots, reinstalls, anything.

## How it works

- `POST /users/{username}` calls `vip.symantec.com` once to register a new credential, then stores `(credentialID, seed)` keyed by username.
- `GET /users/{username}/token` looks up the seed and returns the current 6-digit TOTP — entirely offline computation.
- `GET /` serves a single-page HTML UI: dropdown of users, big token display, 30-second countdown bar, click-to-copy, and a `+ new user` button that registers right from the browser.
- `GET /users` and `DELETE /users/{username}` round out the CRUD.

All endpoints accept an optional `X-API-Key` header. If the `API_KEY` environment variable is set, requests without a matching key are rejected. If unset (default), there is no auth — the server is expected to bind to `127.0.0.1` and rely on host login as the auth boundary.

## Files

- `app/main.py` — the entire server: FastAPI routes, provisioning helper, JSON-file storage, and the inline HTML/JS UI. Single file, ~270 lines.
- `requirements.txt` — pinned dependencies: fastapi, uvicorn, python-vipaccess, oath.
- `install.bat` — one-click Windows installer: checks Python, creates venv + installs deps, makes `%LOCALAPPDATA%\vip-token-server`, drops a `VIP Token` shortcut on the Desktop.
- `install-embedded.bat` — same as `install.bat` but **no admin and no system Python required**. Downloads Python 3.12 embeddable ZIP from python.org and uses it locally. Use this if you can't install Python on the VM.
- `launch.py` — what the desktop shortcut runs. Detects whether the server is already up; spawns a hidden detached uvicorn if not; then opens the browser to the UI.
- `uninstall.bat` — stops the running server (via PID file) and removes the desktop shortcut. Leaves `venv\`, `python\` and `credentials.json` in place (delete by hand if you want).
- `run.bat` — manual launcher with a visible console (use for debugging when something's wrong).
- `register.bat` — register a user from cmd: `register.bat alice`.
- `.gitignore` — excludes `venv/`, `__pycache__/`, `credentials.json`, `.server.pid`, etc. **Never commit `credentials.json`** — it is the entire security boundary.

## Running locally (macOS / Linux)

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
DATA_PATH=./credentials.json venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Open <http://127.0.0.1:8080>. Click `+ new user` to register your first user.

## Installing on a Windows VM (the intended deployment)

### One-click install (recommended)

1. Install Python 3.10+ from <https://www.python.org/downloads/> — during install, check **"Add python.exe to PATH"**.
2. `git clone https://github.com/yihuashub/vip-token-server.git` (or download the ZIP and extract). **Do not copy a macOS/Linux `venv/` over** — let the installer build a Windows one.
3. Double-click **`install.bat`**. It will:
   - verify Python is installed
   - create `venv\` and install dependencies (~2-3 min on first run)
   - create `%LOCALAPPDATA%\vip-token-server\` for the seed store
   - drop **`VIP Token`** on your Desktop (uses the Windows key icon)
4. Double-click the `VIP Token` shortcut. The server starts silently in the background and your default browser opens to <http://localhost:8080>.
5. Click `+ new user` to register the first credential.

Subsequent double-clicks just open the browser — the server keeps running until the VM reboots (no boot-time auto-start, by design).

### No admin rights on the VM? Use `install-embedded.bat` instead

If your company VM blocks the python.org installer (no admin, UAC denial, group policy, etc.), `install-embedded.bat` is the universal fallback. **No system Python required, no admin, no installer wizard.**

It downloads the official Python 3.12 *embeddable* ZIP (about 10 MB) from python.org, extracts it into a `python\` folder inside the project, bootstraps `pip` via `get-pip.py`, then installs the dependencies — all into the project folder. Nothing touches the registry, `Program Files`, or system PATH.

Requirements: outbound HTTPS to `python.org` and `pypi.org` must work. Everything else stays the same — same desktop shortcut, same UI, same launch behavior.

> **Tip:** Even with the regular installer, you don't need admin if you uncheck **"Install for all users"** in the python.org installer's first page — it installs to `%LOCALAPPDATA%\Programs\Python\` instead. Try this before the embedded route.

### Uninstall

Double-click `uninstall.bat`. It stops the server and removes the Desktop shortcut. `credentials.json`, the `venv\` folder, and the `python\` folder (if you used the embedded install) are left alone — delete by hand if you really want them gone.

### Advanced / debugging

Use `run.bat` instead of the shortcut to see uvicorn's log output in a console window. This is the right tool when something is broken and you need to see why.

### Auto-start at boot (rarely needed)

If you want the server to come up automatically at VM boot (so the first user after a reboot doesn't have to start it), install it as a service with [NSSM](https://nssm.cc/download):

```cmd
nssm install VIPTokenServer C:\vip-token-server\venv\Scripts\uvicorn.exe
nssm set    VIPTokenServer AppParameters "app.main:app --host 127.0.0.1 --port 8080"
nssm set    VIPTokenServer AppDirectory   C:\vip-token-server
nssm set    VIPTokenServer AppEnvironmentExtra DATA_PATH=C:\ProgramData\vip-token-server\credentials.json
nssm set    VIPTokenServer Start SERVICE_AUTO_START
nssm start  VIPTokenServer
```

(NSSM requires admin rights to install, and the service runs as `LocalSystem` from boot — that's why we use `C:\ProgramData` here instead of the per-user `%LOCALAPPDATA%`.) This is an alternative to the Desktop shortcut, not an addition — if you set up NSSM, double-clicking the shortcut still works (it just sees the server is already up and opens the browser).

## Configuration (environment variables)

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATA_PATH` | `%LOCALAPPDATA%\vip-token-server\credentials.json` on Windows, `./credentials.json` elsewhere | Where to read/write the seed store. Override to put it on a backed-up drive. |
| `API_KEY` | unset (no auth) | If set, all endpoints require `X-API-Key: <value>`. Recommended only if you intentionally expose beyond localhost. |
| `TOKEN_MODEL` | `VSST` | Default provisioning model. `VSST` = desktop token (compatible with most US financial services). `VSMT` = mobile token. Override per-call with `?token_model=VSMT`. |

## Security model

This server is designed for a **single trusted host, multiple trusted users** scenario.

- The server binds to `127.0.0.1` only. Access requires being logged into the host (RDP, ssh, local console). **VM login is the auth.**
- `credentials.json` IS the secret. Anyone with that file can generate every user's TOTP forever. Back it up to a password manager (1Password / Bitwarden); restrict file ACL to administrators only.
- No rate limiting, no audit log, no per-user permissions — every logged-in host user can read every other user's token. This is by design (the original use case is a shared 2FA terminal).
- **Never expose this server to a public network** or bind it to `0.0.0.0` without an `API_KEY` and a reverse proxy with TLS.

## Operational notes

- **3-year credential lifetime**: VSST/VSMT credentials issued by python-vipaccess expire ~3 years after provisioning. Before expiry, call `POST /users/{username}?force=true` to issue a new one, then re-bind on the target service.
- **Clock sync is critical**: TOTP windows are 30 seconds. Clock skew beyond ~30s produces codes the target service will reject. On Windows VMs, verify Internet time sync is enabled (Control Panel → Date and Time → Internet Time). On macOS/Linux, ensure NTP is running.
- **Coexistence with the official desktop client**: the official Symantec VIP Access app and python-vipaccess credentials are completely independent — separate registrations at `vip.symantec.com`. You can have both at once.
- **Target-service compatibility**: most US brokerages accept `VSST` (desktop) prefixes. A few legacy systems only accept `VSMT` (mobile). If a service rejects your credential ID, re-register with `?token_model=VSMT`.

## Validating a credential

If a target service rejects a token, verify the credential itself is valid first:

```bash
venv/bin/vipaccess check --secret <BASE32_SEED> --identity <VSST_OR_VSMT_ID>
```

This POSTs to Symantec's validation API with the current code. `Token is valid and working` means the issue is elsewhere (target service hasn't been re-bound, clock skew, target uses a non-Symantec MFA stack, etc.).

## License

Unspecified. The underlying [python-vipaccess](https://github.com/dlenski/python-vipaccess) library is GPLv3. If you intend to fork or redistribute, add an explicit `LICENSE` file.
