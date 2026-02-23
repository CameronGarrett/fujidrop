# fujidrop

Self-hosted Frame.io Camera-to-Cloud replacement for Fujifilm cameras.
Your photos and videos upload straight from camera to your home server —
no Frame.io account, no cloud, no subscription.

## How It Works

```
Camera  --WiFi-->  api.frame.io  --DNS rewrite-->  Your server
                   (port 443)                       (fujidrop container)
```

Fujifilm cameras with Frame.io C2C support connect to `api.frame.io` over
HTTPS to upload files. fujidrop emulates that API inside a Docker container
on your local network. A DNS rewrite points `api.frame.io` at your server,
and a custom CA certificate loaded on the camera lets it trust the connection.

The camera thinks it's talking to Frame.io. Your files never leave your network.

## Compatible Cameras

Any Fujifilm camera with native Frame.io Camera-to-Cloud support will work.
Check that your firmware meets the minimum version where listed.

| Camera | Min. Firmware | Notes |
|--------|---------------|-------|
| X-H2S | 4.00 | Needs FT-XH grip below fw 6.00 |
| X-H2 | 2.00 | Needs FT-XH grip below fw 4.00 |
| GFX100 II | — | |
| GFX100S II | — | |
| GFX100RF | — | |
| GFX Eterna 55 | — | Cinema camera; WiFi + Ethernet |
| X100VI | — | |
| X-T5 | 3.01 | |
| X-T50 | — | |
| X-S20 | 2.01 | |
| X-M5 | — | |
| X-E5 | — | |
| X-T30 III | — | |

## Prerequisites

- Docker and Docker Compose
- DNS you can add rewrites to (NextDNS, Pi-hole, router, dnsmasq, etc.)
- Your camera's SD card (to load the CA certificate once)

## Quick Start

### 1. Configure

```bash
git clone https://github.com/CameronGarrett/fujidrop.git
cd fujidrop
cp .env.example .env
```

Edit `.env` and set your NAS IP and volume paths:

```
NAS_IP=192.168.0.100
APPDATA_PATH=/mnt/user/appdata/fujidrop    # certs + config (Unraid)
UPLOAD_PATH=/mnt/user/data/camera-uploads  # photos land here (Unraid)
```

For non-Unraid setups, the defaults (`./certs` and `./uploads`) work fine.
Port 443 must be available on the host (the camera connects to standard HTTPS).

### 2. Build and Start

```bash
docker compose up -d
```

On first start, the container generates CA and server certificates automatically.
Check the logs to confirm:

```bash
docker compose logs
```

### 3. Test (Without the Camera)

Run the test script from any machine on your network to verify the full
upload flow:

```bash
./scripts/test-upload.sh YOUR_NAS_IP
```

This simulates a camera pairing, creating an asset, and uploading a file.
All 5 checks should pass before connecting your real camera.

### 4. Load CA Certificate on Camera

1. Copy `certs/ca.crt` to the **root** of your camera's SD card
2. Insert the SD card into your camera
3. On camera: **Network/USB Setting** > **ROOT CERTIFICATE**
4. Select `ca.crt` and confirm

This tells the camera to trust your server's HTTPS certificate.
The cert is valid for 10 years. This does not modify your camera in any
permanent way — the certificate can be removed at any time through the same menu.

### 5. Configure DNS Rewrite

You need `api.frame.io` to resolve to your server's local IP. Use whichever
DNS tool you have:

**NextDNS:**
Settings > Rewrites > add `api.frame.io` > your NAS IP.
If it doesn't take effect, check that DNS Rebinding Protection isn't blocking
private IP responses.

**Pi-hole:** Local DNS Records > add `api.frame.io` > NAS IP

**dnsmasq:** `address=/api.frame.io/192.168.0.100`

**Router:** Some routers support custom DNS entries in their admin UI.

### 6. Pair Camera

1. Connect your camera to your home WiFi
   - **Network/USB Setting** > **Frame.io Camera to Cloud** > **CONNECT**
2. Start pairing:
   - **Frame.io Camera to Cloud** > **PAIRING (Frame.io)**
3. The camera displays a 6-digit code — after a few seconds it will
   auto-pair (the server approves all codes automatically)
4. You should see "Connected" on the camera

### 7. Configure Upload Settings

On the camera, under **Frame.io Camera to Cloud** > **UPLOAD SETTING**:

| Setting | Recommended |
|---------|-------------|
| AUTO IMAGE TRANSFER ORDER | ON — auto-uploads every shot |
| SELECT FILE TYPE | Enable whichever you want: JPEG, RAW, HEIF, MOV, etc. |
| IMAGE TRANSFER WHILE POWER OFF | ON — continues uploading after power off |
| TRANSFER/SUSPEND | TRANSFER — starts uploading immediately |

## Where Files Go

Uploaded files are saved to the `uploads/` volume, organized by date:

```
uploads/
├── 2025-03-15/
│   ├── DSCF0001.JPG
│   ├── DSCF0001.RAF
│   └── DSCF0002.JPG
└── 2025-03-16/
    └── ...
```

Full-resolution files are uploaded — the same JPEGs, RAW (.RAF), HEIF, and
video files written to your SD card. The camera never deletes files from the
card; fujidrop receives copies.

## Dashboard

Access the dashboard at `https://YOUR_NAS_IP/` (accept the self-signed
certificate warning, or add the CA cert to your system's trust store).

Shows server status, camera pairing state, and recent uploads. The CA
certificate is also available for download at `https://YOUR_NAS_IP/ca.crt`.

## Unraid Deployment

1. Copy this project to `/boot/config/plugins/compose.manager/projects/fujidrop/`
2. Create `.env` from the example and set your values:
   ```
   NAS_IP=192.168.0.100
   APPDATA_PATH=/mnt/user/appdata/fujidrop
   UPLOAD_PATH=/mnt/user/data/camera-uploads
   ```
3. In the Unraid UI: **Docker** > **Compose** > **fujidrop** > **Compose Up**

Certs live on the NVMe cache (appdata), uploads go to the array (parity-protected).
DIUN will automatically pick up image updates since the compose file uses
`ghcr.io/camerongarrett/fujidrop:latest`.

## Troubleshooting

**Camera shows "Connection Error" during pairing**
- Verify DNS rewrite is active: `nslookup api.frame.io` should return your NAS IP
- Verify the container is running: `docker compose ps`
- Verify port 443 is reachable: `curl -k https://YOUR_NAS_IP/`
- Check container logs: `docker compose logs -f`

**Camera pairs but uploads fail**
- Check logs for error details: `docker compose logs -f`
- Run the test script to isolate the issue
- Make sure the upload directory is writable

**DNS rewrite not working (NextDNS)**
- Disable DNS Rebinding Protection in NextDNS Security settings
- Verify your device is using NextDNS: `test.nextdns.io`
- Clear DNS cache on your router if applicable

**Camera won't load the CA certificate**
- Make sure the file is at the root of the SD card (not in a subfolder)
- Try renaming `ca.crt` to `ca.pem` — some firmware versions prefer `.pem`

**Port 443 already in use**
- On Unraid: change the management HTTPS port in Settings > Management Access
- Find what's using it: `ss -tlnp | grep 443`

## Removing / Reverting

1. Delete the DNS rewrite in your DNS settings
2. On camera: **Network/USB Setting** > **ROOT CERTIFICATE** > remove
3. `docker compose down`

No permanent changes are made to your camera. You're back to stock in 30 seconds.

## How It Works (Technical)

fujidrop emulates these Frame.io C2C API endpoints:

| Endpoint | Purpose |
|----------|---------|
| `POST /v2/auth/device/code` | Returns pairing code (auto-approved) |
| `POST /v2/auth/token` | Issues access/refresh tokens |
| `GET /v2/me` | Fake user profile for connection verification |
| `POST /v2/devices/assets` | Creates asset, returns upload URLs |
| `PUT /upload/{id}?part=N` | Receives ~25 MiB file chunks, streams to disk |
| `POST /v2/devices/assets/{id}/realtime-upload-parts` | Additional URLs for video |
| `/v2/*` catch-all | Returns 200 for unknown endpoints, logs for debugging |

The camera authenticates via OAuth 2.0 Device Code Grant (the server
auto-approves all codes), creates assets via JSON API, then uploads file
chunks to presigned-style URLs that point back to the server itself. Unknown
API calls are logged and return 200 so the camera never errors out.

## Credits

Inspired by the [Roach](https://cazander.ca/2024/realfakeframe.io/) project
by cazander, who first demonstrated that Frame.io C2C could be intercepted
locally. Built using Frame.io's
[public C2C API documentation](https://developer.frame.io/docs/device-integrations/concepts-and-fundamentals).

## License

[AGPL-3.0](LICENSE)
