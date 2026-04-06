#!/bin/bash
set -e

# Start Cloudflare WARP proxy via wireproxy if credentials are configured.
# Set WARP_PRIVATE_KEY and WARP_ADDRESS in Railway env vars.
# Generate credentials once with: docker run --rm ghcr.io/virbr/wgcf:latest register --accept-tos && wgcf generate
# Then read PrivateKey and Address from the generated wgcf-profile.conf.

if [ -n "$WARP_PRIVATE_KEY" ] && [ -n "$WARP_ADDRESS" ]; then
    echo "[WARP] Writing wireproxy config..."
    cat > /tmp/wireproxy.conf << EOF
[Interface]
Address = ${WARP_ADDRESS}
DNS = 1.1.1.1
PrivateKey = ${WARP_PRIVATE_KEY}
MTU = 1280

[Peer]
PublicKey = bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=
AllowedIPs = 0.0.0.0/0
Endpoint = engage.cloudflareclient.com:2408

[Socks5]
BindAddress = 127.0.0.1:1080
EOF
    wireproxy -c /tmp/wireproxy.conf &
    WIREPROXY_PID=$!
    echo "[WARP] wireproxy started (PID $WIREPROXY_PID) on 127.0.0.1:1080"
    # Give wireproxy time to establish the WireGuard tunnel
    sleep 4
else
    echo "[WARP] WARP_PRIVATE_KEY not set — running without proxy (local dev mode)"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8080
