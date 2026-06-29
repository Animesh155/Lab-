#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  opcua-secure/up.sh — flip plc-opcua into Basic256Sha256 mode
#
#  Restarts the plc-opcua container with OPCUA_SECURITY=basic256sha256
#  so the next OPC UA write attempt is rejected at the SecurityCheck
#  layer rather than succeeding silently.
#
#  Run from the phase1_env directory:
#    bash lab_protocols/opcua-secure/up.sh
#
#  Revert with:
#    bash lab_protocols/opcua-secure/down.sh
# ══════════════════════════════════════════════════════════════
set -euo pipefail

cd "$(dirname "$0")/../.."   # → phase1_env/

PROJECT="${COMPOSE_PROJECT:-lab_recon}"

echo "==> recreating plc-opcua with OPCUA_SECURITY=basic256sha256"
docker rm -f plc-opcua >/dev/null 2>&1 || true

docker run -d --name plc-opcua \
   --network "${PROJECT}_ot-net" \
   --hostname plc-opcua \
   --restart unless-stopped \
   -e OPCUA_SECURITY=basic256sha256 \
   "${PROJECT}-plc-opcua"

echo "==> waiting for cert generation + server startup (10 s)"
sleep 10

echo "==> latest plc-opcua log (look for 'Basic256Sha256'):"
docker logs --tail 20 plc-opcua

cat <<'EOF'

────────────────────────────────────────────────────────────
 plc-opcua is now in SECURE mode.

 Try the attack — it should be rejected at the handshake:
   docker exec -it attacker bash
   python3 /lab/tools/attack.py --protocol opcua \
           --tag P1_TIT01_temperature_1 --value 99.9

 Expected:  BadSecurityChecksFailed

 Revert with:
   bash lab_protocols/opcua-secure/down.sh
────────────────────────────────────────────────────────────
EOF
