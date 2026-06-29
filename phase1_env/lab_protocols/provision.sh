#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  lab_protocols — Module 5 provision script
#
#  Brings up the base diode stack + lab_recon overlay + the
#  lab_protocols overlay (which mounts tools/ and pcaps/ into
#  the attacker container and gives it ot-net reachability).
#
#  Then captures a 30-second multi-protocol PCAP into
#  lab_protocols/pcaps/multi.pcap — students decode this in §1.2.
#
#  Run from the phase1_env directory:
#    bash lab_protocols/provision.sh
#
#  Teardown:
#    docker compose -p lab_recon down
# ══════════════════════════════════════════════════════════════
set -euo pipefail

cd "$(dirname "$0")/.."   # → phase1_env/

PROJECT=lab_recon

echo "==> building & starting the lab stack (base + recon + protocols)"
# Skip the legacy Node-RED ot-simulator — it binds host port 1880
# and isn't used by any of Modules 1-5. The `|| true` swallows any
# secondary failure from that service so provisioning continues.
docker compose \
  -f docker-compose.yml \
  -f lab_recon/docker-compose.lab.yml \
  -f lab_protocols/docker-compose.lab.yml \
  -p "$PROJECT" \
  up -d --build --scale ot-simulator=0 \
  || true

echo
echo "==> waiting for PLCs to settle (8 s)"
sleep 8

echo
echo "==> sanity check — all three PLCs reachable from attacker"
docker exec attacker bash -lc '
  set +e
  for hp in plc-modbus:502 plc-s7:102 plc-opcua:4840; do
    host="${hp%%:*}"; port="${hp##*:}"
    if (echo > "/dev/tcp/$host/$port") 2>/dev/null; then
      echo "  OK  $hp"
    else
      echo "  FAIL $hp"
    fi
  done
'

# ── Generate the multi-protocol PCAP students decode in §1.2 ────
PCAP_OUT=lab_protocols/pcaps/multi.pcap
echo
if [ -s "$PCAP_OUT" ]; then
  echo "==> $PCAP_OUT already exists, skipping capture"
else
  echo "==> capturing 30 s of multi-protocol traffic → $PCAP_OUT"
  mkdir -p "$(dirname "$PCAP_OUT")"

  # One in-container shell does the whole capture cycle: start
  # tcpdump in background, sleep, run the three attacks, sleep, then
  # SIGINT tcpdump so it flushes and exits cleanly. Keeping it all in
  # a single `docker exec` avoids the session-teardown races we hit
  # when backgrounding `docker exec` from the host.
  # Only the attacker container can capture, and only its own
  # outbound traffic — ot-proxy↔PLC chatter never leaves the ot-net
  # bridge, so we generate 5 rounds of cross-protocol traffic
  # ourselves to give students enough frames to decode in §1.2.
  docker exec attacker bash -lc '
    tcpdump -i any -nn -w /lab/pcaps/multi.pcap \
            "tcp port 502 or tcp port 102 or tcp port 4840" 2>/dev/null &
    TPID=$!
    sleep 2
    for i in 1 2 3 4 5; do
      python3 /lab/tools/attack.py --protocol modbus --tag 0 --value "$i"          >/dev/null
      python3 /lab/tools/attack.py --protocol s7     --tag 0 --value "$((i * 10))" >/dev/null
      python3 /lab/tools/attack.py --protocol opcua  --tag P1_TIT01_temperature_1 --value "$i.5" >/dev/null
      sleep 1
    done
    sleep 2
    kill -INT "$TPID" 2>/dev/null || true
    wait "$TPID" 2>/dev/null || true
  ' 2>&1 | sed "s/^/  /"

  if [ -s "$PCAP_OUT" ]; then
    echo "==> multi.pcap captured ($(du -h "$PCAP_OUT" | cut -f1))"
  else
    echo "==> WARNING: multi.pcap is missing or empty — check tcpdump on attacker"
  fi
fi

cat <<'EOF'

════════════════════════════════════════════════════════════
 Module 5 ready.

 Student entrypoint:
   docker exec -it attacker bash

 Inside:
   /lab/tools/             attack.py, browse_opcua.py, subscribe_opcua.py
                            + your_s7_client.py + your_opcua_client.py
   /lab/pcaps/multi.pcap   30 s capture of all three protocols

 Task sheet:   lab_protocols/TASK_SHEET.md
 Answer key:   lab_protocols/ANSWER_KEY.md   (instructor only)

 Security flip:
   bash lab_protocols/opcua-secure/up.sh       (Basic256Sha256)
   bash lab_protocols/opcua-secure/down.sh     (back to default)

 Teardown:
   docker compose -p lab_recon down
════════════════════════════════════════════════════════════
EOF
