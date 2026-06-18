# Module 1 — Answer Key (Instructor only)

> **Do not distribute to students.** This is what they should
> arrive at, plus the lecture points to make during debrief.

---

## Expected lab state

Networks (set by `docker-compose.lab.yml`):

| Network | Subnet | What lives there |
|---|---|---|
| `lab_recon_ot-net` | `172.20.10.0/24` | `plc-modbus`, `ot-simulator` (Node-RED), `ot-proxy` |
| `lab_recon_diode-net` | `172.20.20.0/24` | `ot-proxy`, `fpga-sim` |
| `lab_recon_it-net` | `172.20.30.0/24` | `fpga-sim`, `it-proxy`, `influxdb`, `grafana`, `attacker` |

The attacker container is on `it-net` only. From there it can
directly reach:

- `influxdb` — **TCP/8086** (shows up on a normal TCP scan)
- `grafana` — **TCP/3000** (shows up on a normal TCP scan)
- `it-proxy` — **UDP/6000** (one-way diode receiver; TCP scan
  misses it, `-sU` shows `open|filtered`)
- `fpga-sim` — **UDP/5000** (one-way diode receiver; also has an
  `it-net` leg, but no TCP listener)

So a default TCP scan reveals only **two** services (8086, 3000);
the two diode receivers are UDP and effectively invisible to a
TCP scan. See §1.2 for why this matters pedagogically.

`plc-modbus` is **not** directly reachable from the attacker —
it's on `ot-net`. Spotting this gap is one of the lab's
intended "aha" moments.

---

## Section 1 — Discovery

### 1.1 Host discovery — expected answer

A reasonable student response:

```bash
nmap -sn 172.20.30.0/24
```

Expected responding hosts (the overlay pins every IP so the
addresses are reproducible across runs and across the
Module 2 / 3 worksheets that reference them):

| IP | Container |
|---|---|
| `172.20.30.1` | docker bridge gateway |
| `172.20.30.2` | `fpga-sim` (it-net leg) |
| `172.20.30.3` | `influxdb` |
| `172.20.30.4` | `it-proxy` |
| `172.20.30.5` | `grafana` |
| `172.20.30.50` | their own attacker container |

(If Module 3's `lab_exploit` overlay is layered on, an extra
host appears at `172.20.30.10` — the `engineering-ws` jumphost.
Pure Module 1 students do not see it.)

**Discussion points for debrief:**

- Many students will scan `172.20.0.0/16` whole. That's 65k hosts
  — `nmap -sn` will be slow. Praise students who narrowed scope
  by trying `172.20.30.0/24` first (their own subnet) and only
  expanding when they didn't find a PLC.
- The "cautious operator" answer: ARP scans (`nmap -PR`),
  passive sniffing first, slower timing (`-T2`), avoid
  `-sS` against port 502.

### 1.2 Port scan — expected ports

**What a default `nmap` scan actually returns.** `nmap` defaults to
a **TCP** scan. The only TCP services on `it-net` are the two
dashboard components:

| Container | Open **TCP** | Notes |
|---|---|---|
| `influxdb` | 8086 | time-series DB |
| `grafana` | 3000 | dashboard web UI |

So a student running `nmap <subnet>` (or `nmap -p- <host>`) sees
**only two open ports**. That surprises people who expect to find
the diode proxies.

**The diode receivers are UDP, not TCP.** Both `fpga-sim` (5000)
and `it-proxy` (6000) `bind()` a **UDP** socket — the data diode
is a one-way *datagram* flow, so there is no TCP listener to find:

| Container | Listener | Why you don't see it on a TCP scan |
|---|---|---|
| `fpga-sim` | **UDP/5000** | one-way ingest from `ot-proxy` |
| `it-proxy` | **UDP/6000** | one-way ingest from `fpga-sim` |

A `-sU` scan *will* surface them, but only as `open|filtered`:

```bash
nmap -sU -p5000 <fpga-sim-ip>     # 5000/udp open|filtered
nmap -sU -p6000 <it-proxy-ip>     # 6000/udp open|filtered
```

The `open|filtered` ambiguity is **correct and instructive**: a
real data diode receiver never replies, so a UDP probe gets no
ICMP-unreachable and no datagram back — nmap cannot prove the port
is open. This is the network signature of a unidirectional
service. Make it a debrief point.

> **Instructor note — the source of truth:**
> ```36:45:phase1_env/fpga_sim/fpga_sim.py
> LISTEN_HOST    = '0.0.0.0'
> LISTEN_PORT    = int(os.environ.get('FPGA_LISTEN_PORT', '5000'))
> ```
> `socket.SOCK_DGRAM` → UDP. Same pattern in `it_proxy.py`.

### 1.3 Role inference — expected guesses

From the **TCP** scan (what most students will have):

- Port **3000** → Grafana (or generic web UI)
- Port **8086** → InfluxDB (or generic DB)

Only students who ran a **UDP** scan (`-sU`) will also have:

- **UDP/5000** → custom one-way service (acceptable)
- **UDP/6000** → custom one-way service (acceptable)

**The trap:** students will look for port 502 in the `it-net`
scan and not find it. The PLC is in `ot-net`, unreachable from
their foothold. **This is the point.** They need to pivot — but
they don't have the pivot yet. Section 2 surfaces this gap.

> **Caveat — Docker hands students the hostnames.** In this
> containerised lab, Docker's embedded DNS answers reverse
> (PTR) lookups, so `nmap` prints names like
> `grafana.lab_recon_it-net`, `influxdb…`, `it-proxy…`,
> `fpga-sim…` *before* the student reasons about any port. The
> "guess the role from ports alone" exercise is therefore
> partly pre-answered here — that is an artifact of the lab
> substrate, **not** something a real flat OT network would
> give an attacker for free. Acknowledge it during debrief:
> ask students what the role inference *would* have required
> on a real network with no helpful DNS (banner-grabbing,
> `-sV`, traffic correlation). If you want the harder version,
> the PTR records can be stripped from the lab.

---

## Section 2 — Fingerprinting

### 2.1 Port 502

- Protocol: **Modbus TCP**
- What its presence means: there is a PLC (or PLC simulator)
  somewhere reachable. Modbus is the oldest still-deployed
  industrial protocol, used everywhere from water treatment to
  oil & gas.

**The catch:** they won't see port 502 in the `it-net` scan.
They have to *discover that they can't reach the PLC directly*
and reason about why. Some will try to pivot through `fpga-sim`
or `ot-proxy`. Both will fail at the network level — that's the
data diode doing its job.

> **Instructor move:** at minute ~20, if no group has figured
> this out, give the hint: "What's on the *other* side of
> 172.20.30.x?"

After the hint, the strong students will use `tcpdump` on a
gateway interface (Section 2.4) to *infer* the existence of
`ot-net` from traffic patterns — without ever reaching it
directly.

### 2.2 Modbus enumeration

Only works if they pivot. If the lab is configured to allow them
to discover the OT subnet via an unintended path, the script
should return a slave ID (typically `1`) and basic device info.

**Acceptable answer if pivoting fails:** "I couldn't reach
port 502 — the network policy blocks me. The diode is enforcing
zone separation."

That's actually the *right* answer for Module 1. Module 3 is
where they get the pivot.

### 2.3 Grafana on port 3000

```bash
curl -s http://172.20.30.x:3000/ | head -40
```

Returns the Grafana app HTML (HTTP 200). **Anonymous auth is
enabled** (`GF_AUTH_ANONYMOUS_ENABLED=true`, Viewer role), so the
attacker needs *no credentials* — the dashboard API is open:

```bash
# list dashboards (no auth needed)
curl -s 'http://172.20.30.x:3000/api/search?type=dash-db'
#   → [{"title":"Data Diode — Live View", "uid":"...", ...}]

# pull the dashboard definition
curl -s 'http://172.20.30.x:3000/api/dashboards/uid/<uid>'
```

What that actually leaks (verified against the provisioned
dashboard — 9 panels titled **"Data Diode — Live View"**):

- The system is explicitly labelled a **data diode**.
- Process variables are exposed by name — the panel/query JSON
  contains **`sensor`, `plc`, `pressure`, `flow`** tags.
- An attacker learns there is a PLC-driven process and what
  physical quantities it controls, **without ever reaching the
  OT network**.

> **Accuracy note for instructors:** the dashboard does *not*
> literally say "water treatment", and the panel count/tag set
> can drift if you edit `dashboard/grafana/dashboards/`. Grade
> on the *concept* (process detail leaked on the IT side), not
> on a specific string. Re-check the live JSON before class if
> you've changed the dashboard.

This is the **information leak**: a dashboard hosted on the
attacker-reachable side that describes the OT process in
detail. Make this a debrief point — defender lesson is
"don't host process-detail dashboards on IT zones."

### 2.4 Passive capture

The attacker container won't see Modbus traffic at all (it's
on a different docker network). Students will report **zero
packets on port 502**. The lesson: you only see what's on
your local segment.

A student who runs `tcpdump -i any` and watches non-502
traffic may see the data flowing out of `it-proxy` toward
`influxdb` — that's how they infer the existence of an
upstream sensor source they can't see directly.

---

## Section 3 — Topology

### 3.1 IT/OT boundary

Expected drawing:

```
  [attacker]──┐
              │
   IT zone:   ├── grafana ── influxdb ── it-proxy ── fpga-sim ═══╗
   172.20.30  │                                                  ║ (one-way)
              └────────────────────────────────────────────────  ║
                                                                 ║
   diode zone:                                                   ▼
   172.20.20                                       ot-proxy ── fpga-sim
                                                       │
   OT zone:                                            │
   172.20.10                                       plc-modbus
```

Boundary evidence:
- Reachability gap (no port 502 from their foothold)
- `fpga-sim` straddles two networks (visible if they look at
  routes carefully)

### 3.2 Targets

- **Physical impact:** the PLC (`plc-modbus`). But they can't
  reach it. So the next-best is whatever device sits between
  them and the PLC — `ot-proxy` if they could compromise the
  IT proxy's send queue, or `fpga-sim` from the diode side.
- **Stealth:** Grafana / InfluxDB — read-only access to the
  process data gives them everything they'd need for
  reconnaissance of a future attack, without touching anything
  that would alarm OT staff.

---

## Section 4 — Reflection

### 4.1 Real incidents to accept

Any of:

- **Davis-Besse nuclear plant (2003)** — Slammer worm and a
  contractor's laptop took the safety display offline for ~5h.
- **Bellingham pipeline (1999)** — IT/SCADA interaction was a
  contributing factor in the rupture investigation.
- **Triton/Trisis (2017)** — though not a scan, the malware
  *did* try to enumerate SIS controllers and triggered a fail-safe.
- **Maroochy Shire (2000)** — disgruntled contractor; relevant
  for the lesson that OT recon is often insider-flavoured.
- Several documented cases of **vulnerability scanners (Nessus,
  Qualys) crashing PLCs** during routine IT audits — there are
  ICS-CERT advisories.

Accept any properly cited incident. **Reject vague pop-culture
references (Stuxnet without specifics, "Ukraine grid").**

### 4.2 Indicators

Strong answers:

| Indicator | Source |
|---|---|
| Burst of SYN packets to many hosts in a short window | Firewall / NetFlow / IDS |
| Unsolicited Modbus function-code reads from a non-master IP | Modbus-aware IDS (Snort + quickdraw, Zeek industrial) |
| New host appearing in ARP tables | Switch logs |
| Failed connection attempts to closed ports | Host firewall logs / Windows event log |

Weak answers (still credit, but push back during debrief):

- "Antivirus" — almost never relevant to OT.
- "User reports" — too slow.

---

## Debrief script (5 min, after the module)

Cover these three points in order:

1. **You hit a wall at the PLC.** That's not a mistake — it's
   the data diode doing exactly what it's designed to do.
   Module 2 is about what an attacker *can* still see (the
   protocol), and Module 3 is about whether the wall is as
   solid as it looks.

2. **Grafana on the IT side is a recon goldmine.** Most plants
   leak process detail through dashboards exactly like this.
   Defender lesson: zone your dashboards, not just your
   networks.

3. **Scanning is loud.** Every student who ran `nmap -sS`
   against the whole `/16` would have been flagged inside the
   first 60 seconds by a half-decent IDS. They got away with
   it because there is no IDS in this lab. We'll add one in
   Module 5.
