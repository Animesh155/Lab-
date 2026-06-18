#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  Lab Modbus (Module 2) — Provisioning script
#
#  Brings up the full stack with Module 1 + Module 2 overlays
#  under the `lab_modbus` project name. Idempotent — safe to
#  re-run.
#
#  What it does:
#    1. Tears down any conflicting compose project (live phase1_env
#       or a previous lab project) so container_names/ports don't
#       collide.
#    2. Builds + starts: base stack + lab_recon overlay (attacker
#       container, pinned subnets) + lab_modbus overlay (mounts
#       /lab/pcaps into the attacker).
#    3. Sanity-checks the PCAP is reachable inside the attacker.
# ══════════════════════════════════════════════════════════════
set -euo pipefail

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PHASE1_DIR="$(cd "$LAB_DIR/.." && pwd)"

cd "$PHASE1_DIR"

PCAP="lab_modbus/pcaps/modbus-baseline.pcapng"
if [[ ! -f "$PCAP" ]]; then
  echo "ERROR: $PCAP not found. Re-capture before running this lab"
  echo "       (see lab_modbus/README.md → 'How the PCAP was generated')."
  exit 1
fi

echo "==> Stopping any conflicting compose projects (container_names clash)"
for proj in phase1_env lab_recon; do
  if docker compose -p "$proj" ps -q 2>/dev/null | grep -q .; then
    echo "   - tearing down project: $proj"
    docker compose -p "$proj" down 2>&1 | tail -3 || true
  fi
done

echo "==> Building & starting lab_modbus (base + Module 1 + Module 2 overlays)"
docker compose \
  -f docker-compose.yml \
  -f lab_recon/docker-compose.lab.yml \
  -f lab_modbus/docker-compose.lab.yml \
  -p lab_modbus \
  up -d --build

echo "==> Waiting for services to come up..."
sleep 8

echo "==> Stack status:"
docker compose -p lab_modbus ps

echo "==> Sanity check — PCAP visible inside attacker container?"
if docker exec attacker test -r /lab/pcaps/modbus-baseline.pcapng; then
  pkts=$(docker exec attacker sh -c \
    "tshark -r /lab/pcaps/modbus-baseline.pcapng -Y modbus 2>/dev/null | wc -l")
  echo "   OK — $pkts Modbus frames in /lab/pcaps/modbus-baseline.pcapng"
else
  echo "   FAIL — PCAP not mounted. Check docker-compose.lab.yml volumes."
  exit 1
fi

cat <<'EOF'

────────────────────────────────────────────────────────────
 Module 2 lab is ready.

 To drop into the attacker shell:
   docker exec -it attacker bash

 The PCAP for this module is at:
   /lab/pcaps/modbus-baseline.pcapng

 Quick smoke test (run inside the container):
   tshark -r /lab/pcaps/modbus-baseline.pcapng -Y modbus | head

 For the Wireshark GUI portion, copy the PCAP to your host:
   docker cp attacker:/lab/pcaps/modbus-baseline.pcapng .
   wireshark modbus-baseline.pcapng

────────────────────────────────────────────────────────────
EOF
