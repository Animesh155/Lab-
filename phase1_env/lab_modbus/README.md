# Lab Modbus — Module 2 (Protocol Fingerprinting)

A 60-minute PCAP-first lab. Students hand-decode Modbus TCP from a
shipped capture, reason about a plant's physical reality from its
register polling pattern, and identify the protocol's missing
security properties — setting up the Module 3 exploitation phase.

## What this lab contains

| File | Purpose |
|---|---|
| `TASK_SHEET.md` | Student worksheet (5 sections, 60 min) |
| `ANSWER_KEY.md` | Instructor-only expected answers + debrief script |
| `pcaps/modbus-baseline.pcapng` | Shipped PCAP (444 packets, 177 s, FC=03 only) |
| `tools/` | Empty here — Module 3 fills it with `rogue_master.py` |
| `docker-compose.lab.yml` | Overlay that mounts `pcaps/` into the attacker container |
| `provision.sh` | Brings up base + Module 1 + Module 2 overlays as project `lab_modbus` |

## How to run it

### Option A — instructor lab VM (cloud-init / on-prem)

```bash
cd phase1_env/lab_modbus
bash provision.sh
```

This stops any conflicting compose project, brings up the full stack
under the `lab_modbus` project name, and verifies the PCAP is
reachable from inside the attacker container.

### Option B — manual

```bash
cd phase1_env
docker compose \
  -f docker-compose.yml \
  -f lab_recon/docker-compose.lab.yml \
  -f lab_modbus/docker-compose.lab.yml \
  -p lab_modbus up -d --build

docker exec -it attacker bash
# inside the container:
ls /lab/pcaps/         # → modbus-baseline.pcapng
tshark -r /lab/pcaps/modbus-baseline.pcapng -Y modbus | head
```

### Wireshark (GUI) on the student's VM

The student does §1 and §2 in Wireshark. Either:
- copy the PCAP off the container (`docker cp attacker:/lab/pcaps/modbus-baseline.pcapng ./`), or
- pre-stage the PCAP at `/home/student/pcaps/` via cloud-init.

Wireshark needs to be installed on the host VM, not in the container.
Add `wireshark` to the cloud-init `packages:` list when provisioning
the student VM.

## How the PCAP was generated

If you ever need to regenerate it (e.g. after changing the polling
rate, register count, or HAI source data):

```bash
# bring up the lab_recon stack so IPs are 172.20.10/24
cd phase1_env
docker compose -f docker-compose.yml -f lab_recon/docker-compose.lab.yml \
  -p lab_recon up -d --build
sleep 10

# capture from inside plc-modbus's network namespace via netshoot
docker run --rm \
  --net=container:plc-modbus \
  -v "$PWD/lab_modbus/pcaps:/out" \
  nicolaka/netshoot \
  tcpdump -i any -nn -w /out/modbus-baseline.pcapng \
           -G 180 -W 1 'tcp port 502'
```

After regenerating, **re-validate** `ANSWER_KEY.md` — the exact
register values in §4.1 change because the HAI replay loops through
real sensor data. Cadence, function code, and register range stay
stable as long as `POLL_INTERVAL`, `MODBUS_PORT`, and the sensor
array length aren't changed in `docker-compose.yml`.

## Why PCAP-first and not live-first

A live capture introduces three variances we don't want at the
learning-the-protocol stage:

1. **Different runs ⇒ different register values** → instructor can't
   write definitive answers.
2. **Network jitter in Docker bridges** ⇒ student stats wander.
3. **Stack-up bugs** ⇒ if `plc-modbus` is wedged, the lab stalls.

A shipped PCAP is **reproducible, gradeable, and stack-independent**.
The trade-off is that students don't get the satisfaction of running
their own `tcpdump`; that comes in Module 3, where the artefact they
produce is *their attack's* PCAP, used as input to the Module 4
defender exercise.

## Dependencies on Module 1

This module's overlay assumes the Module 1 `attacker` image is built
(it provides `tshark`, `tcpdump`, `python3`, `pymodbus`). If Module 1
hasn't been run, `provision.sh` will build it as part of the cascade.
