import base64
import io
import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import quote

import oath
import qrcode
import qrcode.image.svg
from fastapi import FastAPI, Header, HTTPException, status
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from vipaccess import provision as vp

DATA_PATH = Path(os.environ.get("DATA_PATH", "credentials.json"))
API_KEY = os.environ.get("API_KEY")  # optional — if unset, no auth (use localhost-only bind)
DEFAULT_TOKEN_MODEL = os.environ.get("TOKEN_MODEL", "VSST")

_lock = threading.Lock()


def _load() -> dict:
    if not DATA_PATH.exists():
        return {}
    with DATA_PATH.open() as f:
        return json.load(f)


def _save(data: dict) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA_PATH.with_suffix(".tmp")
    with tmp.open("w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    tmp.replace(DATA_PATH)


def _provision(token_model: str) -> dict:
    request = vp.generate_request(token_model=token_model)
    session = vp.requests.Session()
    response = vp.get_provisioning_response(request, session)
    otp_token = vp.get_token_from_response(response.content)
    otp_secret = vp.decrypt_key(otp_token["iv"], otp_token["cipher"])
    if not vp.check_token(otp_token, otp_secret, session):
        raise RuntimeError(
            "Symantec rejected the newly-issued token; "
            "system clock likely skewed beyond tolerance"
        )
    return {
        "credential_id": otp_token["id"],
        "secret_b32": base64.b32encode(otp_secret).upper().decode("ascii"),
        "expiry": otp_token["expiry"],
        "token_model": token_model,
        "created_at": int(time.time()),
    }


def _totp(secret_b32: str) -> tuple[str, int]:
    seed_hex = base64.b32decode(secret_b32).hex()
    now = int(time.time())
    return oath.totp(seed_hex, t=now), 30 - now % 30


def _otpauth_uri(credential_id: str, secret_b32: str) -> str:
    """RFC 6238 / Google Authenticator key URI for this credential."""
    issuer = "Symantec"
    label = quote(f"{issuer}:{credential_id}", safe="")
    return (
        f"otpauth://totp/{label}"
        f"?secret={secret_b32}"
        f"&issuer={issuer}"
        f"&digits=6&algorithm=SHA1&period=30"
    )


def _auth(x_api_key: str | None) -> None:
    if API_KEY is None:
        return
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key"
        )


app = FastAPI(title="VIP Token Server", docs_url="/docs", redoc_url=None)


class RegisterResponse(BaseModel):
    username: str
    credential_id: str
    expiry: str
    token_model: str


class TokenResponse(BaseModel):
    username: str
    credential_id: str
    token: str
    seconds_until_next: int


class UserInfo(BaseModel):
    credential_id: str
    expiry: str
    token_model: str


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>VIP Token</title>
<style>
  body { font-family: -apple-system, "Segoe UI", system-ui, sans-serif;
         max-width: 480px; margin: 40px auto; padding: 0 20px; color: #222; }
  .header { display: flex; align-items: center; justify-content: space-between;
            margin-bottom: 12px; }
  h1 { font-size: 14px; color: #888; font-weight: 600; letter-spacing: 2px; margin: 0; }
  .add-btn { background: none; border: 1px solid #ddd; color: #4a8; cursor: pointer;
             font-size: 13px; padding: 4px 10px; border-radius: 4px; }
  .add-btn:hover { background: #f4faf7; }
  select { width: 100%; padding: 10px; font-size: 16px; border: 1px solid #ccc;
           border-radius: 4px; box-sizing: border-box; }
  .add-form { display: flex; gap: 6px; margin-top: 8px; }
  .add-form input { flex: 1; padding: 9px; font-size: 14px; border: 1px solid #ccc;
                    border-radius: 4px; box-sizing: border-box; }
  .add-form button { padding: 8px 14px; font-size: 13px; border: 1px solid #ccc;
                     background: white; border-radius: 4px; cursor: pointer; }
  .add-form button[type=submit] { background: #4a8; border-color: #4a8; color: white; }
  .add-form button:disabled { opacity: 0.5; cursor: wait; }
  .status { font-size: 12px; color: #c33; margin-top: 6px; min-height: 16px; }
  .status.info { color: #888; }
  .token { font-size: 56px; font-family: ui-monospace, Menlo, Consolas, monospace;
           letter-spacing: 8px; text-align: center; margin: 36px 0 8px;
           cursor: pointer; user-select: all; }
  .token:hover { color: #4a8; }
  .meta { text-align: center; color: #888; font-size: 13px; }
  .bar { height: 4px; background: #eee; border-radius: 2px; overflow: hidden;
         margin-top: 18px; }
  .fill { height: 100%; background: #4a8; transition: width 1s linear; }
  .cred { font-family: ui-monospace, Menlo, Consolas, monospace; color: #aaa;
          font-size: 11px; text-align: center; margin-top: 24px; }
  .empty { color: #aaa; text-align: center; padding: 60px 0; font-size: 14px; }
  .copied { color: #4a8 !important; }
  .phone-btn { display: block; margin: 20px auto 0; background: none; border: 1px solid #ddd;
               color: #888; cursor: pointer; font-size: 12px; padding: 5px 12px; border-radius: 4px; }
  .phone-btn:hover { color: #4a8; border-color: #4a8; }
  .qr-panel { margin-top: 16px; padding: 14px; border: 1px solid #eee;
              border-radius: 6px; background: #fafafa; }
  .qr-panel img { display: block; margin: 8px auto; max-width: 240px; height: auto; }
  .qr-warn { font-size: 11px; color: #b85; text-align: center; margin-top: 8px;
             line-height: 1.5; }
  .qr-uri { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 10px;
            color: #aaa; word-break: break-all; margin-top: 10px; padding: 6px;
            background: white; border-radius: 3px; user-select: all; cursor: text; }
</style>
</head>
<body>
<div class="header">
  <h1>VIP TOKEN</h1>
  <button id="addBtn" class="add-btn">+ new user</button>
</div>
<select id="user"><option>loading...</option></select>
<form id="addForm" class="add-form" hidden>
  <input id="addName" placeholder="username (e.g. alice)" autocomplete="off">
  <button type="submit" id="addSubmit">Add</button>
  <button type="button" id="addCancel">cancel</button>
</form>
<div id="status" class="status"></div>
<div id="display" class="empty">Select a user above</div>

<script>
const $ = id => document.getElementById(id);
const sel = $('user'), addBtn = $('addBtn'), addForm = $('addForm'),
      addName = $('addName'), addSubmit = $('addSubmit'),
      addCancel = $('addCancel'), status = $('status'), display = $('display');

async function loadUsers(selectName) {
  const r = await fetch('/users');
  const users = await r.json();
  const names = Object.keys(users).sort();
  if (names.length === 0) {
    sel.innerHTML = '<option value="">(no users — click "+ new user")</option>';
  } else {
    sel.innerHTML = '<option value="">— select user —</option>' +
      names.map(u => `<option value="${u}">${u}  (${users[u].credential_id})</option>`).join('');
  }
  if (selectName) { sel.value = selectName; refresh(); }
}

let currentUser = null;

function bindTokenClick(token) {
  $('tok').onclick = (e) => {
    navigator.clipboard.writeText(token);
    e.target.classList.add('copied');
    setTimeout(() => e.target.classList.remove('copied'), 600);
  };
}

async function refresh() {
  const u = sel.value;
  if (!u) {
    display.className = 'empty';
    display.textContent = names_present() ? 'Select a user above' : 'No users yet';
    currentUser = null;
    qrShownFor = null;
    return;
  }
  const r = await fetch(`/users/${encodeURIComponent(u)}/token`);
  if (!r.ok) { display.className = 'empty'; display.textContent = 'error'; return; }
  const d = await r.json();
  const pct = (d.seconds_until_next / 30) * 100;

  if (u !== currentUser) {
    // user changed — rebuild the whole display (collapses any open QR)
    display.className = '';
    display.innerHTML = `
      <div class="token" id="tok" title="click to copy">${d.token}</div>
      <div class="meta" id="meta">expires in ${d.seconds_until_next}s</div>
      <div class="bar"><div class="fill" id="fill" style="width:${pct}%"></div></div>
      <div class="cred">${d.credential_id}</div>
      <button class="phone-btn" id="phoneBtn">Show QR for phone</button>
      <div id="qrPanel"></div>`;
    $('phoneBtn').onclick = () => togglePhoneQR(u);
    currentUser = u;
    qrShownFor = null;
  } else {
    // same user — only update the parts that change, leave QR panel intact
    $('tok').textContent = d.token;
    $('meta').textContent = `expires in ${d.seconds_until_next}s`;
    $('fill').style.width = pct + '%';
  }
  bindTokenClick(d.token);
}

let qrShownFor = null;
async function togglePhoneQR(u) {
  const panel = $('qrPanel');
  const btn = $('phoneBtn');
  if (qrShownFor === u) {
    panel.innerHTML = '';
    btn.textContent = 'Show QR for phone';
    qrShownFor = null;
    return;
  }
  panel.innerHTML = '<div class="qr-panel" style="text-align:center;color:#888;font-size:13px">loading...</div>';
  const r = await fetch(`/users/${encodeURIComponent(u)}/uri`);
  if (!r.ok) { panel.innerHTML = '<div class="qr-panel">error</div>'; return; }
  const d = await r.json();
  panel.innerHTML = `
    <div class="qr-panel">
      <img src="/users/${encodeURIComponent(u)}/qr.svg" alt="QR code">
      <div class="qr-warn">
        Scan with any TOTP app (Google Authenticator / Microsoft Authenticator / Authy / 1Password).<br>
        Symantec's own VIP Access app does NOT accept third-party imports.<br>
        <b>This QR contains the seed — anyone who sees it can compute tokens forever.</b>
      </div>
      <div class="qr-uri" title="otpauth URI (manual entry fallback)">${d.uri}</div>
    </div>`;
  btn.textContent = 'Hide QR';
  qrShownFor = u;
}

function names_present() {
  return sel.options.length > 1 || (sel.options[0] && sel.options[0].value);
}

addBtn.onclick = () => {
  addBtn.hidden = true;
  addForm.hidden = false;
  status.textContent = '';
  addName.focus();
};
addCancel.onclick = () => {
  addForm.hidden = true;
  addBtn.hidden = false;
  addName.value = '';
  status.textContent = '';
};
addForm.onsubmit = async (e) => {
  e.preventDefault();
  const name = addName.value.trim();
  if (!name) return;
  addSubmit.disabled = true;
  status.className = 'status info';
  status.textContent = 'provisioning with Symantec... (~2s)';
  try {
    const r = await fetch(`/users/${encodeURIComponent(name)}`, { method: 'POST' });
    const d = await r.json();
    if (r.ok) {
      addName.value = '';
      addForm.hidden = true;
      addBtn.hidden = false;
      status.className = 'status info';
      status.textContent = `✓ ${name} → ${d.credential_id}`;
      setTimeout(() => { status.textContent = ''; }, 4000);
      await loadUsers(name);
    } else {
      status.className = 'status';
      const msg = (d.detail && d.detail.error) || d.detail || `HTTP ${r.status}`;
      const extra = d.detail && d.detail.credential_id ? ` (existing: ${d.detail.credential_id})` : '';
      status.textContent = msg + extra;
    }
  } catch (err) {
    status.className = 'status';
    status.textContent = 'network error: ' + err.message;
  } finally {
    addSubmit.disabled = false;
  }
};

sel.addEventListener('change', refresh);
loadUsers();
setInterval(refresh, 1000);
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index():
    return INDEX_HTML


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/users", response_model=dict[str, UserInfo])
def list_users(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    _auth(x_api_key)
    with _lock:
        data = _load()
    return {
        u: UserInfo(
            credential_id=info["credential_id"],
            expiry=info["expiry"],
            token_model=info["token_model"],
        )
        for u, info in data.items()
    }


@app.post("/users/{username}", response_model=RegisterResponse, status_code=201)
def register(
    username: str,
    token_model: str = DEFAULT_TOKEN_MODEL,
    force: bool = False,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _auth(x_api_key)
    with _lock:
        data = _load()
        if username in data and not force:
            existing = data[username]
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "user already registered",
                    "credential_id": existing["credential_id"],
                    "hint": "pass ?force=true to issue a new credential "
                    "(old one becomes orphan at Symantec)",
                },
            )
        cred = _provision(token_model)
        data[username] = cred
        _save(data)
    return RegisterResponse(
        username=username,
        credential_id=cred["credential_id"],
        expiry=cred["expiry"],
        token_model=cred["token_model"],
    )


@app.get("/users/{username}/token", response_model=TokenResponse)
def get_token(
    username: str, x_api_key: str | None = Header(default=None, alias="X-API-Key")
):
    _auth(x_api_key)
    with _lock:
        data = _load()
    if username not in data:
        raise HTTPException(status_code=404, detail="username not registered")
    info = data[username]
    code, sec = _totp(info["secret_b32"])
    return TokenResponse(
        username=username,
        credential_id=info["credential_id"],
        token=code,
        seconds_until_next=sec,
    )


@app.get("/users/{username}/uri")
def get_uri(
    username: str, x_api_key: str | None = Header(default=None, alias="X-API-Key")
):
    """Return the otpauth:// URI for importing this credential into a third-party
    TOTP app (Google Authenticator, Authy, 1Password, Microsoft Authenticator, ...).
    Anyone who can read this URI can compute the user's TOTPs forever — treat it
    as a secret."""
    _auth(x_api_key)
    with _lock:
        data = _load()
    if username not in data:
        raise HTTPException(status_code=404, detail="username not registered")
    info = data[username]
    return {
        "username": username,
        "credential_id": info["credential_id"],
        "uri": _otpauth_uri(info["credential_id"], info["secret_b32"]),
    }


@app.get("/users/{username}/qr.svg")
def get_qr(
    username: str, x_api_key: str | None = Header(default=None, alias="X-API-Key")
):
    """Return the otpauth URI rendered as an SVG QR code so a phone TOTP app
    can scan it directly. Same secrecy caveat as /uri — anyone who sees the QR
    has the seed."""
    _auth(x_api_key)
    with _lock:
        data = _load()
    if username not in data:
        raise HTTPException(status_code=404, detail="username not registered")
    info = data[username]
    uri = _otpauth_uri(info["credential_id"], info["secret_b32"])
    img = qrcode.make(
        uri,
        image_factory=qrcode.image.svg.SvgPathImage,
        box_size=10,
        border=2,
    )
    buf = io.BytesIO()
    img.save(buf)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")


@app.delete("/users/{username}", status_code=204)
def delete_user(
    username: str, x_api_key: str | None = Header(default=None, alias="X-API-Key")
):
    _auth(x_api_key)
    with _lock:
        data = _load()
        if username not in data:
            raise HTTPException(status_code=404, detail="username not registered")
        del data[username]
        _save(data)
