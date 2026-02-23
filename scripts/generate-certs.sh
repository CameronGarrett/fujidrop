#!/usr/bin/env bash
set -euo pipefail

# Generate a CA certificate (goes on the camera) and a server certificate
# (used by the container) valid for api.frame.io.

CERT_DIR="${1:-./certs}"
NAS_IP="${2:-${NAS_IP:-192.168.0.100}}"

mkdir -p "$CERT_DIR"

if [ -f "$CERT_DIR/ca.crt" ] && [ -f "$CERT_DIR/server.crt" ]; then
    echo "Certificates already exist in $CERT_DIR — skipping generation."
    echo "  Delete $CERT_DIR to regenerate."
    exit 0
fi

echo "Generating certificates..."
echo "  NAS IP: $NAS_IP"
echo "  Output: $CERT_DIR"

# --- CA (Certificate Authority) ---
openssl genrsa -out "$CERT_DIR/ca.key" 4096 2>/dev/null

openssl req -new -x509 \
    -key "$CERT_DIR/ca.key" \
    -sha256 \
    -days 3650 \
    -out "$CERT_DIR/ca.crt" \
    -subj "/CN=FujiDrop CA"

# --- Server certificate for api.frame.io ---
openssl genrsa -out "$CERT_DIR/server.key" 2048 2>/dev/null

# CSR
openssl req -new \
    -key "$CERT_DIR/server.key" \
    -out "$CERT_DIR/server.csr" \
    -subj "/CN=api.frame.io"

# SAN config — the cert is valid for both the Frame.io domain and your NAS IP
cat > "$CERT_DIR/_san.cnf" <<EOF
[v3_ext]
subjectAltName = DNS:api.frame.io, DNS:*.frame.io, IP:${NAS_IP}
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
EOF

# Sign with our CA
openssl x509 -req \
    -in "$CERT_DIR/server.csr" \
    -CA "$CERT_DIR/ca.crt" \
    -CAkey "$CERT_DIR/ca.key" \
    -CAcreateserial \
    -out "$CERT_DIR/server.crt" \
    -days 3650 \
    -sha256 \
    -extensions v3_ext \
    -extfile "$CERT_DIR/_san.cnf"

# Clean up temp files
rm -f "$CERT_DIR/server.csr" "$CERT_DIR/_san.cnf" "$CERT_DIR/ca.srl"

echo ""
echo "Done! Certificates generated:"
echo "  $CERT_DIR/ca.crt      — load this onto your camera (ROOT CERTIFICATE)"
echo "  $CERT_DIR/server.crt  — used by the server (auto-configured)"
echo "  $CERT_DIR/server.key  — used by the server (auto-configured)"
