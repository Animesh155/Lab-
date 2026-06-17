#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  Lab Recon — Provisioning script
#
#  Called by cloud-init on first boot. Also safe to re-run by
#  hand (idempotent) when iterating on the lab.
#
#  What it does:
#    1. Builds the attacker container image
#    2. Brings up the base diode stack + the lab overlay
#    3. Waits for healthchecks
# ══════════════════════════════════════════════════════════════
set -euo pipefail

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PHASE1_DIR="$(cd "$LAB_DIR/.." && pwd)"

cd "$PHASE1_DIR"

echo "==> Building & starting the lab stack"
docker compose \
  -f docker-compose.yml \
  -f lab_recon/docker-compose.lab.yml \
  -p lab_recon \
  up -d --build

echo "==> Waiting for services to come up..."
sleep 8

echo "==> Stack status:"
docker compose -p lab_recon ps

cat <<'EOF'

────────────────────────────────────────────────────────────
 Lab is ready.

 To drop into the attacker shell:
   docker exec -it attacker bash

 Inside the attacker container, the brief is at:
   cat /brief.txt

────────────────────────────────────────────────────────────
EOF
