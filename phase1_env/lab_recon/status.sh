#!/usr/bin/env bash
# Quick sanity check the instructor (or student) can run to see
# if the lab stack is healthy.
set -euo pipefail

echo "── Containers ──────────────────────────────────────────"
docker compose -p lab_recon ps

echo
echo "── Networks (expect 3 subnets: 10.x, 20.x, 30.x) ───────"
docker network ls --filter name=lab_recon --format \
  'table {{.Name}}\t{{.Driver}}\t{{.Scope}}'
for net in lab_recon_ot-net lab_recon_diode-net lab_recon_it-net; do
  echo
  echo "  $net:"
  docker network inspect "$net" \
    --format '    subnet={{(index .IPAM.Config 0).Subnet}}' \
    2>/dev/null || echo "    (not present)"
done

echo
echo "── Attacker container reachable? ───────────────────────"
if docker exec attacker true 2>/dev/null; then
  echo "  yes — drop in with:  docker exec -it attacker bash"
else
  echo "  NO — attacker container is not running"
fi
