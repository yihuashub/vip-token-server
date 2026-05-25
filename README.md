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
- `run.bat` — Windows launcher: creates the venv on first run, installs deps, sets `DATA_PATH=C:\vip-data\credentials.json`, starts uvicorn on `127.0.0.1:8080`.
- `register.bat` — Windows helper for registering a user from cmd: `register.bat alice`.
- `.gitignore` — excludes `venv/`, `__pycache__/`, `credentials.json`, etc. **Never commit `credentials.json`** — it is the entire security boundary.

## Running locally (macOS / Linux)

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
DATA_PATH=./credentials.json venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Open <http://127.0.0.1:8080>. Click `+ new user` to register your first user.

## Running on a Windows VM (the intended deployment)

1. Install Python 3.11+ from python.org (check "Add to PATH" during install).
2. Copy the project folder to the VM. **Do not copy `venv/`** — the macOS/Linux venv will not work on Windows; `run.bat` rebuilds it.
3. Double-click `run.bat`. First run creates the venv and installs deps (~3 minutes; pycryptodome may need to compile). Subsequent runs start in ~2 seconds.
4. Anyone who RDPs into the VM opens <http://localhost:8080> in a browser and selects their username from the dropdown.

### Auto-start at boot (optional, via NSSM)

Download [NSSM](https://nssm.cc/download), unzip, then in an Administrator cmd:

```cmd
nssm install VIPTokenServer C:\vip-token-server\venv\Scripts\uvicorn.exe
nssm set    VIPTokenServer AppParameters "app.main:app --host 127.0.0.1 --port 8080"
nssm set    VIPTokenServer AppDirectory   C:\vip-token-server
nssm set    VIPTokenServer AppEnvironmentExtra DATA_PATH=C:\vip-data\credentials.json
nssm set    VIPTokenServer Start SERVICE_AUTO_START
nssm start  VIPTokenServer
```

After this the service runs as `LocalSystem` from boot, no login required.

## Configuration (environment variables)

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATA_PATH` | `credentials.json` (cwd) | Where to read/write the seed store. On Windows, set to an absolute path outside the project dir. |
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
