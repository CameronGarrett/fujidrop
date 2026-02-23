#!/usr/bin/env bash
set -euo pipefail

# ===================================================================
#  fujidrop — Test Script
#  Simulates a Fujifilm camera's full upload flow to verify your
#  server is working before connecting the real camera.
#
#  Usage:  ./scripts/test-upload.sh <NAS_IP>
#  Example: ./scripts/test-upload.sh 192.168.0.100
# ===================================================================

NAS_IP="${1:?Usage: $0 <NAS_IP>}"
BASE="https://${NAS_IP}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CA="${SCRIPT_DIR}/../certs/ca.crt"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}PASS${NC}  $1"; }
fail() { echo -e "  ${RED}FAIL${NC}  $1"; exit 1; }
info() { echo -e "  ${YELLOW}....${NC}  $1"; }

echo ""
echo "=== fujidrop Test ==="
echo "    Server: $BASE"
echo ""

# --- Check CA cert exists ---
if [ ! -f "$CA" ]; then
    fail "CA certificate not found at $CA
       Start the container first:  docker compose up -d"
fi

# --- 1. Connectivity ---
echo "[1/5] Connectivity"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --cacert "$CA" "$BASE/" 2>/dev/null) || true
if [ "$HTTP_CODE" = "200" ]; then
    pass "Server reachable (HTTPS verified with CA cert)"
else
    fail "Could not connect (HTTP $HTTP_CODE)
       Is the container running?  docker compose ps
       Is port 443 open?  curl -k https://${NAS_IP}/"
fi

# --- 2. Device pairing ---
echo "[2/5] Device pairing (POST /v2/auth/device/code)"
RESPONSE=$(curl -s --cacert "$CA" -X POST "$BASE/v2/auth/device/code" \
    -F "client_id=test-fuji-xe5" \
    -F "client_secret=test" \
    -F "scope=asset_create offline")

DEVICE_CODE=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['device_code'])" 2>/dev/null) \
    || fail "Bad response from /v2/auth/device/code: $RESPONSE"
USER_CODE=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['user_code'])")
pass "Got pairing code: $USER_CODE"

# --- 3. Token exchange ---
echo "[3/5] Token exchange (POST /v2/auth/token)"
RESPONSE=$(curl -s --cacert "$CA" -X POST "$BASE/v2/auth/token" \
    -F "client_id=test-fuji-xe5" \
    -F "client_secret=test" \
    -F "grant_type=urn:ietf:params:oauth:grant-type:device_code" \
    -F "device_code=$DEVICE_CODE")

TOKEN=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null) \
    || fail "Bad response from /v2/auth/token: $RESPONSE"
pass "Got access token"

# --- 4. Asset creation + upload ---
echo "[4/5] Asset creation + file upload"

# Create a 100 KB test file
TEST_FILE=$(mktemp)
dd if=/dev/urandom of="$TEST_FILE" bs=1024 count=100 2>/dev/null
FILESIZE=$(wc -c < "$TEST_FILE" | tr -d ' ')

info "Creating asset (${FILESIZE} bytes)..."
RESPONSE=$(curl -s --cacert "$CA" -X POST "$BASE/v2/devices/assets" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -H "x-client-version: 1.00" \
    -d "{\"name\":\"TEST_UPLOAD_$(date +%H%M%S).JPG\",\"filetype\":\"image/jpeg\",\"filesize\":$FILESIZE}")

ASSET_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null) \
    || fail "Bad response from /v2/devices/assets: $RESPONSE"
UPLOAD_URL=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['upload_urls'][0])")

# Replace api.frame.io hostname with the actual NAS IP for direct testing
UPLOAD_URL=$(echo "$UPLOAD_URL" | sed "s|https://api.frame.io|$BASE|")

info "Uploading file..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --cacert "$CA" -X PUT "$UPLOAD_URL" \
    -H "Content-Type: application/octet-stream" \
    --data-binary "@$TEST_FILE")

rm -f "$TEST_FILE"

if [ "$HTTP_CODE" = "200" ]; then
    pass "File uploaded and saved"
else
    fail "Upload failed (HTTP $HTTP_CODE)"
fi

# --- 5. Verify via API ---
echo "[5/5] Verify upload"
RESPONSE=$(curl -s --cacert "$CA" "$BASE/api/uploads")
COUNT=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len([u for u in d['uploads'] if 'TEST_UPLOAD' in u['name']]))" 2>/dev/null) || COUNT=0

if [ "$COUNT" -gt 0 ]; then
    pass "Upload confirmed in server records"
else
    fail "Upload not found in server records"
fi

echo ""
echo -e "${GREEN}=== All tests passed ===${NC}"
echo ""
echo "Your server is working. Next steps:"
echo ""
echo "  1. Copy certs/ca.crt to your camera's SD card"
echo "  2. On camera: Network/USB Setting > ROOT CERTIFICATE > load ca.crt"
echo "  3. In NextDNS: Settings > Rewrites > add:  api.frame.io -> $NAS_IP"
echo "  4. Connect camera to your home WiFi"
echo "  5. On camera: Network/USB Setting > Frame.io > pair"
echo "     (it will auto-approve in a few seconds)"
echo ""
