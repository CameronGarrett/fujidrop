#!/usr/bin/env bash
set -euo pipefail

CERT_DIR="${CERT_DIR:-/certs}"
NAS_IP="${NAS_IP:-192.168.0.100}"

# Generate certificates on first run
if [ ! -f "$CERT_DIR/ca.crt" ] || [ ! -f "$CERT_DIR/server.crt" ]; then
    echo "=== First run — generating certificates ==="
    /app/scripts/generate-certs.sh "$CERT_DIR" "$NAS_IP"
    echo ""
    echo "============================================"
    echo "  IMPORTANT: Copy $CERT_DIR/ca.crt to your"
    echo "  camera's SD card and load it via:"
    echo "    Network/USB Setting > ROOT CERTIFICATE"
    echo "============================================"
    echo ""
fi

echo "Starting fujidrop server..."
echo "  HTTPS: 0.0.0.0:443  (camera connects here)"
echo "  Uploads: ${UPLOAD_DIR:-/uploads}"
echo ""

exec uvicorn app.server:app \
    --host 0.0.0.0 \
    --port 443 \
    --ssl-keyfile "$CERT_DIR/server.key" \
    --ssl-certfile "$CERT_DIR/server.crt" \
    --log-level "${LOG_LEVEL:-info}" \
    --no-access-log
