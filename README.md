# framedrop

Self-hosted Frame.io Camera-to-Cloud replacement. Your photos and videos
upload straight from camera to your home server — no Frame.io account,
no cloud, no subscription.

## How It Works

```
Camera  --WiFi-->  api.frame.io  --DNS rewrite-->  Your server
                   (port 443)                       (framedrop container)
```

Cameras with native Frame.io C2C support connect to `api.frame.io` over
HTTPS to upload files. framedrop emulates that API inside a Docker container
on your local network. A DNS rewrite points `api.frame.io` at your server,
and a custom CA certificate loaded on the camera lets it trust the connection.

The camera thinks it's talking to Frame.io. Your files never leave your network.

## Compatible Cameras

Any camera with native Frame.io Camera-to-Cloud support and the ability to
load a custom root certificate should work. Cameras listed below are from
brands with documented CA certificate loading.

| Brand | Camera | Notes | Confirmed Firmware |
|-------|--------|-------|--------------------|
| Canon | EOS C400 | C2C added in fw 1.0.2.1 | — |
| Canon | EOS C80 | C2C added in fw 1.0.2.1 | — |
| Canon | EOS C50 | | — |
| Fujifilm | GFX100 II | | — |
| Fujifilm | GFX100S II | | — |
| Fujifilm | GFX100RF | | — |
| Fujifilm | GFX Eterna 55 | Cinema camera; WiFi + Ethernet | — |
| Fujifilm | X100VI | C2C added in fw 1.30 | — |
| Fujifilm | X-E5 | | — |
| Fujifilm | X-H2 | Needs FT-XH grip below fw 4.00 | — |
| Fujifilm | X-H2S | Needs FT-XH grip below fw 6.00 | — |
| Fujifilm | X-M5 | | — |
| Fujifilm | X-S20 | C2C added in fw 2.01 | — |
| Fujifilm | X-T5 | C2C added in fw 3.01 | — |
| Fujifilm | X-T30 III | | — |
| Fujifilm | X-T50 | | — |
| Panasonic | LUMIX GH7 | | — |
| Panasonic | LUMIX S1II | | — |
| Panasonic | LUMIX S1IIE | Video-oriented S1II variant | — |
| Panasonic | LUMIX S1RII | | — |
| Panasonic | LUMIX S5II | C2C added in fw 3.0 | — |
| Panasonic | LUMIX S5IIX | C2C added in fw 2.0 | — |

If you've confirmed a camera and firmware version, please open a PR to fill
in the "Confirmed Firmware" column.

## Prerequisites

- Docker and Docker Compose
- DNS you can add rewrites to (NextDNS, Pi-hole, router, dnsmasq, etc.)
- Your camera's memory card (to load the CA certificate once)

## Quick Start

### 1. Configure

```bash
git clone https://github.com/CameronGarrett/framedrop.git
cd framedrop
cp .env.example .env
```

Edit `.env` and set at minimum your server's IP:

```
NAS_IP=192.168.0.100
```

Volume paths default to `./certs` and `./uploads` in the project directory.
See `.env.example` for all options. Port 443 must be available on the host
(the camera connects to standard HTTPS).

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

Copy `certs/ca.crt` to your camera's memory card and load it as a root
certificate. The process varies by brand:

#### Fujifilm

1. Copy `ca.crt` to the **root** of your SD card
2. On camera: **Network/USB Setting** > **ROOT CERTIFICATE**
3. Select `ca.crt` and confirm

Some firmware versions prefer `.pem` — try renaming to `ca.pem` if the
camera doesn't recognize the file. Frame.io and FTP share the same root
certificate store on Fujifilm cameras.

See: [Fujifilm C2C QuickStart Guide](https://help.frame.io/en/articles/7156603-c2c-fujifilm-quickstart-guide)

#### Panasonic LUMIX

1. Copy `ca.crt` to the **root** of your memory card (`.pem`, `.cer`, and
   `.crt` are all accepted)
2. On camera: **Setup** > **Others** > **Root Certificate** > **Load**
3. Select the certificate file

Panasonic cameras can store up to 6 root certificates simultaneously.

See: [Panasonic LUMIX C2C QuickStart Guide](https://help.frame.io/en/articles/9179663-c2c-panasonic-lumix-quickstart-guide)

#### Canon

1. Rename `ca.crt` to exactly **`ROOT.CRT`** (Canon requires this filename;
   `ROOT.CER` and `ROOT.PEM` also work)
2. Copy to your memory card
3. On camera: **Network Settings** > **Connection option settings** >
   **FTP transfer settings** > **Set root certif** > **Load root certif from card**

See: [Canon C2C QuickStart Guide](https://help.frame.io/en/articles/10070093-c2c-canon-quickstart-guide)

---

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
2. Start Frame.io pairing in your camera's network settings
   - **Fujifilm**: Network/USB Setting > Frame.io Camera to Cloud > CONNECT,
     then PAIRING (Frame.io)
   - **Panasonic**: Setup > Others > Frame.io > Connect
   - **Canon**: Network Settings > Frame.io > Connect
3. The camera displays a pairing code — after a few seconds it will
   auto-pair (the server approves all codes automatically)
4. You should see a connected/paired status on the camera

### 7. Configure Upload Settings

Enable automatic uploads in your camera's Frame.io / C2C settings. The exact
menu varies by brand, but generally you want:

- **Auto transfer**: ON — uploads every shot automatically
- **File types**: enable whichever you want (JPEG, RAW, video, etc.)
- **Transfer while power off**: ON if available — continues uploading after
  the camera sleeps

Refer to your camera's manual or the Frame.io QuickStart guide for your brand.

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

Full-resolution files are uploaded — the same files written to your memory
card. The camera never deletes files from the card; framedrop receives copies.

## Dashboard

Access the dashboard at `http://YOUR_NAS_IP:3000/`. This is plain HTTP on
a separate port — no certificate warning in your browser.

Shows server status, camera pairing state, and recent uploads. The CA
certificate is also available for download at `http://YOUR_NAS_IP:3000/ca.crt`.

The dashboard is also available on port 443 (`https://YOUR_NAS_IP/`) if you
prefer, but you'll need to accept the self-signed certificate warning.

## Unraid Deployment

1. Copy this project to `/boot/config/plugins/compose.manager/projects/framedrop/`
2. Create `.env` from the example and set your values:
   ```
   NAS_IP=192.168.0.100
   CERT_PATH=/mnt/user/appdata/framedrop
   UPLOAD_PATH=/mnt/user/data/camera-uploads
   ```
3. In the Unraid UI: **Docker** > **Compose** > **framedrop** > **Compose Up**

Certs go to appdata, uploads go to wherever you point them.

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
- Make sure the file is at the root of the memory card (not in a subfolder)
- Check the filename requirements for your brand (Canon requires `ROOT.CRT`)
- Verify the camera's date/time is correct (certificate validation is
  time-dependent)

**Port 443 already in use**

The camera connects to `api.frame.io` on port 443 (standard HTTPS) — this
cannot be changed. If another service on your server already uses port 443,
you have a few options:

- **Move the other service** to a different port. For example, on Unraid,
  change the management HTTPS port in Settings > Management Access to
  something like 3443.
- **Reverse proxy with SNI passthrough**: if you run a reverse proxy (Nginx
  Proxy Manager, Traefik, Caddy), configure it to pass TLS connections for
  SNI hostname `api.frame.io` through to framedrop on an internal port,
  while handling all other traffic normally.
- **Dedicated IP via Docker macvlan**: give the framedrop container its own
  IP address on your LAN so it gets its own port 443 without conflicting.

Find what's using port 443: `ss -tlnp | grep 443`

## Removing / Reverting

1. Delete the DNS rewrite in your DNS settings
2. Remove the root certificate from your camera
3. `docker compose down`

No permanent changes are made to your camera. You're back to stock in 30 seconds.

## Technical Overview

framedrop emulates these Frame.io C2C API endpoints:

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
