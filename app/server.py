"""
framedrop - Self-hosted Frame.io Camera-to-Cloud emulator.

Emulates the Frame.io C2C API so cameras with native C2C support can upload
photos and videos directly to your home server without a Frame.io account.
"""

import os
import uuid
import shutil
import random
import logging
import asyncio
import html as html_mod
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, APIRouter, Request, Response
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/uploads"))
CERT_DIR = Path(os.getenv("CERT_DIR", "/certs"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "3000"))

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("framedrop")

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------

device_codes: dict = {}
tokens: dict = {}
assets: dict = {}
upload_log: list = []          # recent uploads shown on dashboard
server_start: datetime = None  # set in lifespan
_assembly_lock = asyncio.Lock()

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global server_start
    server_start = datetime.now(timezone.utc)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_parts()
    _scan_existing_uploads()

    # Start plain HTTP dashboard server
    config = uvicorn.Config(
        dashboard_app, host="0.0.0.0", port=DASHBOARD_PORT,
        log_level=LOG_LEVEL.lower(), access_log=False,
    )
    dashboard_server = uvicorn.Server(config)
    dashboard_task = asyncio.create_task(dashboard_server.serve())

    logger.info("framedrop server started")
    logger.info(f"  Camera API (HTTPS): port 443")
    logger.info(f"  Dashboard (HTTP):   port {DASHBOARD_PORT}")
    logger.info(f"  Uploads directory:  {UPLOAD_DIR}")
    logger.info(f"  Certificates:       {CERT_DIR}")
    yield

    dashboard_server.should_exit = True
    await dashboard_task

app = FastAPI(title="framedrop", docs_url=None, redoc_url=None, lifespan=lifespan)

# Dashboard app — plain HTTP on a separate port, shares state with main app
dashboard_app = FastAPI(title="framedrop dashboard", docs_url=None, redoc_url=None)
dashboard_router = APIRouter()

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@dashboard_router.get("/", response_class=HTMLResponse)
async def dashboard():
    uptime = _format_uptime()
    total_files = len(upload_log)
    total_bytes = sum(f["size"] for f in upload_log)
    total_size = _human_size(total_bytes)
    paired = len(device_codes) > 0

    rows = ""
    for f in upload_log[:50]:
        ts = f["timestamp"][:19].replace("T", " ")
        safe_name = html_mod.escape(f["name"])
        safe_dir = html_mod.escape(f.get("directory", ""))
        rows += (
            f"<tr>"
            f"<td>{safe_name}</td>"
            f"<td>{_human_size(f['size'])}</td>"
            f"<td>{safe_dir}</td>"
            f"<td>{ts}</td>"
            f"</tr>\n"
        )

    if not rows:
        rows = '<tr><td colspan="4" style="text-align:center;color:#888">No uploads yet</td></tr>'

    status_color = "#4ade80"
    pair_color = "#4ade80" if paired else "#888"
    pair_text = "Paired" if paired else "Waiting"

    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>framedrop</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, system-ui, sans-serif; background:#111; color:#e5e5e5; padding:2rem; }}
  h1 {{ font-size:1.5rem; font-weight:600; margin-bottom:1.5rem; }}
  .status {{ display:flex; gap:2rem; margin-bottom:2rem; flex-wrap:wrap; }}
  .card {{ background:#1a1a1a; border:1px solid #333; border-radius:8px; padding:1rem 1.5rem; min-width:160px; }}
  .card .label {{ font-size:0.75rem; text-transform:uppercase; color:#888; margin-bottom:0.25rem; }}
  .card .value {{ font-size:1.25rem; font-weight:600; }}
  .dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; position:relative; top:-1px; }}
  table {{ width:100%; border-collapse:collapse; margin-top:1rem; }}
  th {{ text-align:left; font-size:0.75rem; text-transform:uppercase; color:#888; padding:0.5rem 1rem; border-bottom:1px solid #333; }}
  td {{ padding:0.5rem 1rem; border-bottom:1px solid #222; font-size:0.9rem; }}
  tr:hover {{ background:#1a1a1a; }}
  a {{ color:#60a5fa; text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
  .section {{ margin-top:2rem; }}
  .section h2 {{ font-size:1.1rem; font-weight:600; margin-bottom:0.75rem; }}
  .muted {{ color:#888; font-size:0.85rem; }}
</style>
</head><body>
<h1>framedrop</h1>
<div class="status">
  <div class="card">
    <div class="label">Server</div>
    <div class="value"><span class="dot" style="background:{status_color}"></span>Running</div>
  </div>
  <div class="card">
    <div class="label">Camera</div>
    <div class="value"><span class="dot" style="background:{pair_color}"></span>{pair_text}</div>
  </div>
  <div class="card">
    <div class="label">Uploads</div>
    <div class="value">{total_files}</div>
  </div>
  <div class="card">
    <div class="label">Total Size</div>
    <div class="value">{total_size}</div>
  </div>
  <div class="card">
    <div class="label">Uptime</div>
    <div class="value">{uptime}</div>
  </div>
</div>

<div class="section">
  <div style="display:flex; justify-content:space-between; align-items:baseline;">
    <h2>Recent Uploads</h2>
    <a href="/ca.crt">Download CA Certificate</a>
  </div>
  <table>
    <tr><th>Filename</th><th>Size</th><th>Folder</th><th>Date</th></tr>
    {rows}
  </table>
</div>

<p class="muted" style="margin-top:2rem">framedrop &mdash; self-hosted Frame.io C2C emulator</p>
</body></html>"""
    return HTMLResponse(html)


@dashboard_router.get("/ca.crt")
async def download_ca_cert():
    ca_path = CERT_DIR / "ca.crt"
    if ca_path.exists():
        return FileResponse(ca_path, filename="ca.crt", media_type="application/x-pem-file")
    return JSONResponse({"error": "CA certificate not generated yet"}, status_code=404)


@dashboard_router.get("/api/status")
async def api_status():
    return {
        "status": "running",
        "uptime": _format_uptime(),
        "total_uploads": len(upload_log),
        "total_size_bytes": sum(f["size"] for f in upload_log),
        "paired_devices": len(device_codes),
        "pending_assets": sum(1 for a in assets.values() if not a.get("complete")),
    }


@dashboard_router.get("/api/uploads")
async def api_uploads():
    return {"uploads": upload_log[:100]}


# Include dashboard routes on both apps:
# - main app (HTTPS 443): camera can also reach the dashboard
# - dashboard_app (HTTP 3000): browser-friendly, no cert warning
app.include_router(dashboard_router)
dashboard_app.include_router(dashboard_router)


# ===================================================================
#  Frame.io C2C API Emulation
# ===================================================================

# ---- Authentication (OAuth 2.0 Device Code Grant) -----------------

@app.post("/v2/auth/device/code")
async def auth_device_code(request: Request):
    """Camera requests a pairing code."""
    form = await request.form()
    client_id = form.get("client_id", "unknown")
    scope = form.get("scope", "")

    user_code = f"{random.randint(100000, 999999)}"
    dc = str(uuid.uuid4())

    device_codes[dc] = {
        "user_code": user_code,
        "client_id": str(client_id),
        "scope": str(scope),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(f"Device pairing requested  code={user_code}  client={client_id}")
    logger.info(f"  Auto-approved (self-hosted mode)")

    return JSONResponse({
        "device_code": dc,
        "user_code": user_code,
        "verification_uri": "https://api.frame.io/device",
        "verification_uri_complete": f"https://api.frame.io/device?code={user_code}",
        "expires_in": 900,
        "interval": 5,
    })


@app.post("/v2/auth/token")
async def auth_token(request: Request):
    """Camera exchanges device code for access token, or refreshes a token."""
    form = await request.form()
    grant_type = str(form.get("grant_type", ""))

    access_token = str(uuid.uuid4())
    refresh_token = str(uuid.uuid4())

    if "device_code" in grant_type:
        dc = str(form.get("device_code", ""))
        if dc not in device_codes:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        logger.info(f"Camera paired successfully  code={device_codes[dc]['user_code']}")
    elif "refresh_token" in grant_type:
        logger.info("Token refreshed")
    else:
        logger.warning(f"Unknown grant_type: {grant_type}")

    tokens[access_token] = {"created_at": datetime.now(timezone.utc).isoformat()}

    return JSONResponse({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 31536000,      # 1 year
        "scope": "asset_create offline",
    })


# ---- User / Account stubs ----------------------------------------
# The camera may call these after pairing to verify the connection.

@app.get("/v2/me")
async def me():
    return JSONResponse({
        "id": "framedrop-user",
        "name": "framedrop",
        "email": "local@framedrop",
        "account_id": "framedrop-account",
    })


@app.get("/v2/accounts/{account_id}")
async def account(account_id: str):
    return JSONResponse({
        "id": account_id,
        "name": "framedrop",
    })


# ---- Asset Management --------------------------------------------

@app.post("/v2/devices/assets")
async def create_asset(request: Request):
    """Camera creates an asset and receives upload URLs."""
    body = await request.json()

    asset_id = str(uuid.uuid4())
    name = Path(body.get("name", f"unknown_{asset_id}")).name or f"unknown_{asset_id}"
    filesize = body.get("filesize")
    filetype = body.get("filetype", "application/octet-stream")
    is_realtime = body.get("is_realtime_upload", False)

    # Calculate number of upload parts (cap at 4000 ≈ 100 GB)
    chunk_size = 25 * 1024 * 1024   # 25 MiB per part
    if filesize and not is_realtime:
        num_parts = min(4000, max(1, (filesize + chunk_size - 1) // chunk_size))
    else:
        num_parts = 1

    # Upload URLs point back to ourselves (camera reaches us via DNS rewrite)
    upload_urls = [
        f"https://api.frame.io/upload/{asset_id}?part={i + 1}"
        for i in range(num_parts)
    ]

    assets[asset_id] = {
        "id": asset_id,
        "name": name,
        "filesize": filesize,
        "filetype": filetype,
        "num_parts": num_parts,
        "parts_received": {},
        "is_realtime": is_realtime,
        "complete": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    fw = request.headers.get("x-client-version", "unknown")
    logger.info(f"Asset created  name={name}  size={filesize}  parts={num_parts}  firmware={fw}")

    return JSONResponse({
        "id": asset_id,
        "name": name,
        "filesize": filesize,
        "filetype": filetype,
        "upload_urls": upload_urls,
        "is_realtime_upload": is_realtime,
    })


@app.post("/v2/devices/assets/{asset_id}/realtime-upload-parts")
async def create_realtime_parts(asset_id: str, request: Request):
    """For real-time uploads (video): camera requests more upload URLs."""
    if asset_id not in assets:
        return JSONResponse({"error": "asset not found"}, status_code=404)

    asset = assets[asset_id]
    next_part = asset.get("_next_realtime_part", asset["num_parts"] + 1)
    batch = 5

    upload_urls = [
        f"https://api.frame.io/upload/{asset_id}?part={next_part + i}"
        for i in range(batch)
    ]
    asset["_next_realtime_part"] = next_part + batch
    asset["num_parts"] = next_part + batch - 1

    return JSONResponse({"upload_urls": upload_urls})


# ---- File Upload --------------------------------------------------

@app.put("/upload/{asset_id}")
async def upload_part(asset_id: str, request: Request):
    """Receive a file chunk from the camera."""
    try:
        part = int(request.query_params.get("part", 1))
    except (ValueError, TypeError):
        return Response(status_code=400)

    if asset_id not in assets:
        logger.warning(f"Upload for unknown asset {asset_id}")
        return Response(status_code=404)

    asset = assets[asset_id]

    # Stream body to disk to avoid holding 25 MiB in memory
    parts_dir = UPLOAD_DIR / ".parts" / asset_id
    parts_dir.mkdir(parents=True, exist_ok=True)
    part_path = parts_dir / f"{part:06d}"

    size = 0
    with open(part_path, "wb") as f:
        async for chunk in request.stream():
            f.write(chunk)
            size += len(chunk)

    asset["parts_received"][part] = size
    logger.info(
        f"  Received part {part}/{asset['num_parts']}  "
        f"{_human_size(size)}  {asset['name']}"
    )

    # Assemble when all parts are in (non-realtime only)
    if not asset["is_realtime"] and len(asset["parts_received"]) >= asset["num_parts"]:
        async with _assembly_lock:
            await asyncio.get_event_loop().run_in_executor(
                None, _assemble_file, asset_id
            )

    return Response(status_code=200)


@app.post("/upload/{asset_id}/complete")
async def complete_realtime_upload(asset_id: str, request: Request):
    """Signal that a real-time upload is finished."""
    if asset_id in assets:
        assets[asset_id]["num_parts"] = len(assets[asset_id]["parts_received"])
        async with _assembly_lock:
            await asyncio.get_event_loop().run_in_executor(
                None, _assemble_file, asset_id
            )
    return Response(status_code=200)


# ---- Catch-all for unknown endpoints -----------------------------

@app.api_route("/v2/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def catch_all_v2(path: str, request: Request):
    """Handle unknown Frame.io API calls gracefully."""
    body_preview = b""
    try:
        body_preview = await request.body()
    except Exception:
        pass

    logger.warning(
        f"Unhandled endpoint  {request.method} /v2/{path}  "
        f"body={body_preview[:200]}"
    )
    # Return 200 so the camera doesn't error out
    return JSONResponse({})


# ===================================================================
#  Helpers
# ===================================================================

def _assemble_file(asset_id: str):
    """Reassemble uploaded parts into the final file."""
    asset = assets[asset_id]
    if asset["complete"]:
        return

    parts_dir = UPLOAD_DIR / ".parts" / asset_id
    if not parts_dir.exists():
        return

    # Organize by date
    today = datetime.now().strftime("%Y-%m-%d")
    output_dir = UPLOAD_DIR / today
    output_dir.mkdir(parents=True, exist_ok=True)

    # Handle filename conflicts
    output_path = output_dir / asset["name"]
    if output_path.exists():
        stem = output_path.stem
        suffix = output_path.suffix
        counter = 1
        while output_path.exists():
            output_path = output_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    # Concatenate parts in order
    part_files = sorted(parts_dir.iterdir(), key=lambda p: p.name)
    with open(output_path, "wb") as out:
        for pf in part_files:
            with open(pf, "rb") as inp:
                shutil.copyfileobj(inp, out)

    # Clean up temp parts
    shutil.rmtree(parts_dir, ignore_errors=True)

    asset["complete"] = True
    file_size = output_path.stat().st_size
    logger.info(f"Saved  {output_path.name}  {_human_size(file_size)}  -> {output_dir}")

    upload_log.insert(0, {
        "name": output_path.name,
        "size": file_size,
        "directory": today,
        "type": asset.get("filetype", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    # Keep log bounded
    while len(upload_log) > 500:
        upload_log.pop()

    # Free memory from completed assets (keep only last 50 incomplete)
    _prune_state()


def _prune_state():
    """Free memory by removing completed assets and old auth entries."""
    # Remove completed assets (files are on disk, metadata is in upload_log)
    completed = [k for k, v in assets.items() if v.get("complete")]
    for k in completed:
        del assets[k]

    # Cap auth dicts — keep only the most recent 100 entries
    if len(device_codes) > 100:
        oldest = sorted(device_codes, key=lambda k: device_codes[k]["created_at"])
        for k in oldest[:-100]:
            del device_codes[k]
    if len(tokens) > 100:
        oldest = sorted(tokens, key=lambda k: tokens[k]["created_at"])
        for k in oldest[:-100]:
            del tokens[k]


def _cleanup_stale_parts():
    """Remove orphaned .parts directories from interrupted uploads."""
    parts_root = UPLOAD_DIR / ".parts"
    if not parts_root.exists():
        return
    removed = 0
    for d in list(parts_root.iterdir()):
        if d.is_dir() and d.name not in assets:
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    if removed:
        logger.info(f"Cleaned up {removed} orphaned partial upload(s)")
    # Remove .parts dir itself if empty
    try:
        parts_root.rmdir()
    except OSError:
        pass


def _scan_existing_uploads():
    """Populate upload_log from files already on disk."""
    if not UPLOAD_DIR.exists():
        return
    files = []
    for f in UPLOAD_DIR.rglob("*"):
        if f.is_file() and not f.name.startswith(".") and ".parts" not in f.parts:
            try:
                stat = f.stat()
                files.append({
                    "name": f.name,
                    "size": stat.st_size,
                    "directory": str(f.parent.relative_to(UPLOAD_DIR)),
                    "type": "",
                    "timestamp": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat(),
                })
            except OSError:
                continue
    files.sort(key=lambda x: x["timestamp"], reverse=True)
    upload_log.extend(files[:500])
    if files:
        logger.info(f"Found {len(files)} existing files in uploads directory")


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} PB"


def _format_uptime() -> str:
    if server_start is None:
        return "—"
    delta = datetime.now(timezone.utc) - server_start
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    hours = secs // 3600
    mins = (secs % 3600) // 60
    if hours < 24:
        return f"{hours}h {mins}m"
    days = hours // 24
    hours = hours % 24
    return f"{days}d {hours}h"
