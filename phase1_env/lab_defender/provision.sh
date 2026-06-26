#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  lab_defender — Module 4 provision script
#
#  Brings up just the `defender-tools` container with the shipped
#  attack pcap mounted at /lab/pcaps/attack.pcap.
#
#  This module does NOT need the base diode stack. The pcap is
#  the only input; everything is offline analysis. So we don't
#  touch lab_recon, lab_modbus, or lab_exploit at all.
#
#  Run from the phase1_env directory:
#    bash lab_defender/provision.sh
#
#  Teardown:
#    docker compose -p lab_defender down
# ══════════════════════════════════════════════════════════════
set -euo pipefail

cd "$(dirname "$0")/.."   # → phase1_env/

echo "==> bringing up lab_defender (defender-tools only)"
# --project-directory . anchors the compose-file's relative
# build-context paths at phase1_env/, matching the convention
# used by lab_recon / lab_modbus / lab_exploit (their compose
# files use `./<lab>/<image>` as context).
docker compose \
   -f lab_defender/docker-compose.lab.yml \
   --project-directory . \
   -p lab_defender \
   up -d --build

echo
echo "==> sanity check — defender-tools is up and tools are installed"
docker exec defender-tools bash -lc '
   echo "Zeek:    $(/opt/zeek/bin/zeek --version 2>&1 | head -1)"
   echo "Snort:   $(snort --version 2>&1 | grep -E Version | head -1)"
   echo "icsnpp:  $(/opt/zeek/bin/zkg list 2>&1 | grep icsnpp || echo NOT INSTALLED)"
   echo "PCAP:    $(ls -lh /lab/pcaps/attack.pcap | awk "{print \$5, \$9}")"
'

echo
echo "==> quick smoke test — Zeek should produce modbus_detailed.log"
docker exec defender-tools bash -lc '
   cd /lab/work
   rm -f *.log
   /opt/zeek/bin/zeek -C -r /lab/pcaps/attack.pcap /lab/zeek/load.zeek
   echo "logs produced:"
   ls /lab/work/
   echo
   writes=$(awk "/^[^#]/ && \$9 ~ /WRITE/" modbus_detailed.log | wc -l)
   echo "FC=06 writes in modbus_detailed.log: $writes (expected: 3)"
'

cat <<'EOF'

════════════════════════════════════════════════════════════
 Module 4 ready.

 Student entrypoint:
   docker exec -it defender-tools bash

 Task sheet:    lab_defender/TASK_SHEET.md
 Answer key:    lab_defender/ANSWER_KEY.md   (instructor only)

 Teardown:
   docker compose -p lab_defender down
════════════════════════════════════════════════════════════
EOF
