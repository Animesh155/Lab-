#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  opcua-secure/down.sh — revert plc-opcua to default (open) mode
#
#  Restarts plc-opcua via docker compose so it picks up the
#  default OPCUA_SECURITY=none again.
# ══════════════════════════════════════════════════════════════
set -euo pipefail

cd "$(dirname "$0")/../.."   # → phase1_env/

PROJECT="${COMPOSE_PROJECT:-lab_recon}"

echo "==> removing the secure plc-opcua container"
docker rm -f plc-opcua >/dev/null 2>&1 || true

echo "==> recreating plc-opcua via docker compose (default config)"
docker compose \
  -f docker-compose.yml \
  -f lab_recon/docker-compose.lab.yml \
  -p "$PROJECT" \
  up -d plc-opcua

echo "==> waiting for server (5 s)"
sleep 5

echo "==> latest plc-opcua log (should say 'SecurityPolicy=None'):"
docker logs --tail 10 plc-opcua

cat <<'EOF'

────────────────────────────────────────────────────────────
 plc-opcua is back in DEFAULT (open) mode.
────────────────────────────────────────────────────────────
EOF
