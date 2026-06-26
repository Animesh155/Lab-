# Module 4 — Defender's View (Zeek + Snort)

Instructor notes for the fourth and final module of the
4-hour OT lab series.

## What this lab teaches

Given the attack PCAP from Module 3, students:

1. Run **Zeek** with the **CISA icsnpp-modbus** parser and read
   `modbus_detailed.log` to identify the rogue master, its
   register operations, and the "invisible writes" the SCADA
   dashboard never saw.
2. Run **Snort 2.9** with an empty `local.rules` against the
   same PCAP and observe **zero alerts** — the central
   distinction between *passive logging* and *signature
   detection*.
3. Write their own Snort rule(s) that detect the attack. The
   instructor reference set has three rules of escalating
   sophistication (source-IP allow-list, FC=06 writes,
   "invisible-write" detector with `byte_test` against the
   register address).
4. Reflect on what their rule misses — spoofed-master attacks,
   compromised legit-master, operator setpoint changes as a
   false-positive vector, read-only reconnaissance.

Time budget: **~50 minutes** end-to-end.

## What this lab does NOT need

Unlike Modules 1-3, this lab is **purely offline**. The shipped
`pcaps/attack.pcap` is the only input. You do not need the
diode base stack, ot-proxy, plc-modbus, Grafana, or any of the
network overlays to be running. The defender-tools container is
network-isolated by design — students aren't sniffing live
traffic, they're doing forensics on a capture.

This makes Module 4 portable: hand a student a USB stick with
the `defender-tools` image + `attack.pcap` and they can do the
whole module on a disconnected laptop.

## File layout

```
lab_defender/
├── README.md                       ← this file
├── TASK_SHEET.md                   ← student worksheet
├── ANSWER_KEY.md                   ← instructor reference (DO NOT show)
├── provision.sh                    ← bring up defender-tools
├── docker-compose.lab.yml          ← single-service overlay
│
├── defender-tools/
│   └── Dockerfile                  ← Ubuntu 22.04 + Zeek + Snort + icsnpp
│
├── pcaps/
│   └── attack.pcap                 ← 271 packets, 88 s, captured during Module 3
│
├── zeek/
│   └── load.zeek                   ← loader (icsnpp-modbus enabled)
│
└── snort/
    ├── snort.conf                  ← minimal config; includes local.rules
    ├── local.rules                 ← empty; students edit this
    └── example.rules               ← instructor reference; 3 working rules
```

## Running the lab

```bash
cd phase1_env
bash lab_defender/provision.sh        # builds image, smoke-tests Zeek+icsnpp

# students do their work
docker exec -it defender-tools bash

# teardown
docker compose -p lab_defender down
```

The provision script will:

1. Build the `defender-tools` image (~1 minute first time, then
   cached).
2. Verify Zeek runs and produces `modbus_detailed.log` with the
   expected 3 FC=06 writes.
3. Print the entrypoint command for students.

## Regenerating the shipped PCAP (instructor only)

If you ever need to re-capture `attack.pcap` — for example,
because you changed the rogue_master.py write addresses or
plant baseline — bring up `lab_exploit` and replay the attack
while capturing on `plc-modbus:eth0`:

```bash
bash lab_exploit/provision.sh
sleep 5

docker run -d --name attack-tcpdump \
   --net=container:plc-modbus \
   -v "$PWD/lab_defender/pcaps:/out" \
   nicolaka/netshoot \
   tcpdump -i eth0 -nn -w /out/attack.pcap -G 90 -W 1 'tcp port 502'

sleep 10
docker exec engineering-ws /lab/tools/rogue_master.py --host 172.20.10.3 read 0 15
sleep 5
docker exec engineering-ws /lab/tools/rogue_master.py --host 172.20.10.3 write 5 9999
sleep 5
docker exec engineering-ws /lab/tools/rogue_master.py --host 172.20.10.3 write 100 42
sleep 5
docker exec engineering-ws /lab/tools/rogue_master.py --host 172.20.10.3 write 500 1

docker wait attack-tcpdump
docker rm attack-tcpdump
bash lab_exploit/teardown.sh
```

**Important:** capture on `eth0` *not* `-i any`. The `any`
interface produces SLL2 (Linux cooked v2) framing, which
Snort 2.9 cannot decode. `eth0` inside `plc-modbus`'s network
namespace produces standard Ethernet frames that both Zeek
and Snort handle natively.

After re-capture, re-run `provision.sh` and check the
answer-key numbers still hold:

| Stat | Expected |
|---|---|
| Packet count | ~270 |
| Capture window | ~88 s |
| TCP convs on :502 | **5** |
| FC=06 writes | **3** |
| Snort R1 alerts | **22** |
| Snort R2 alerts | **3** |
| Snort R3 alerts | **2** |

If any of those drift significantly, re-derive the answer key.

## Design notes

### Why Snort 2.9 and not Snort 3?

Snort 3's `modbus` inspector is cleaner and supports
`modbus_func:write_single_register` natively. We deliberately
use Snort 2.9 here for two reasons:

1. The Ubuntu 22.04 `snort` package is Snort 2.9; it installs
   in one line with no source build needed, which keeps the
   Dockerfile small and reliable.
2. The Snort 2.9 Ubuntu build doesn't include the dynamic
   Modbus preprocessor either, so the rules use **raw byte
   matching** (`content:"|06|"; offset:7; depth:1`). This is
   pedagogically aligned with the Module 2 PCAP-first lesson
   where students hand-decoded the Modbus byte layout. They
   re-use that knowledge here.

If you want to upgrade this lab to Snort 3 + native Modbus
support, the rule logic stays the same — only the syntax
changes. The pcap and answer-key counts remain valid.

### Why icsnpp-modbus?

Stock Zeek's `modbus.log` gives you source IP, function code,
and transaction ID per frame. That's enough to identify "two
masters talking, one is rogue", but it doesn't show *which
register* was written. The CISA/INL `icsnpp-modbus` package
adds `modbus_detailed.log` with `address`, `quantity`, and
`request_values` / `response_values` columns — exactly what
students need to see the difference between "write to register
5" (visible) and "write to register 100" (invisible).

The package is installed at container build time via `zkg`.
The loader (`zeek/load.zeek`) explicitly loads it via
`@load packages/icsnpp-modbus`.

### Why no `local.rules` content?

The whole point of §4 is the student writing the rule. Starting
with an empty file forces them to think about the matching
criteria themselves. `example.rules` is for the instructor's
post-hoc validation, not for students to copy.
