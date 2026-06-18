# Module 2 — Answer Key (Instructor only)

> **Do not distribute to students.** This is what they should arrive
> at, plus the lecture points to make during debrief.

---

## What the shipped PCAP contains

File: `pcaps/modbus-baseline.pcapng`
Captured from the `lab_recon` stack with `plc-modbus` (slave) and
`ot-proxy` (master) on the pinned subnet `172.20.10.0/24`.

| Property | Value |
|---|---|
| Total packets | 444 |
| Duration | ~177 s |
| TCP conversations | 1 |
| Master (TCP client) | `172.20.10.4:43488` (ot-proxy ephemeral) |
| Slave (TCP server) | `172.20.10.3:502` (plc-modbus) |
| Modbus frames | 296 (148 requests + 148 responses) |
| Function codes seen | **3 (Read Holding Registers) — only** |
| Register access pattern | FC=03, start=0, count=15 (every single poll) |
| Polling cadence | ~1.20 s (POLL_INTERVAL=1.0 in compose + overhead) |
| Response latency | ~0.4–5 ms (loopback Docker bridge) |
| Transaction IDs | Monotonically increasing from 17 |
| Unit ID | 1 (only) |
| Writes / exceptions / diagnostics | **None** |

The capture is deliberately boring — that's the point. A real OT
network spends 99% of its life looking exactly like this. The
*absence* of variety is the lesson.

---

## Section 1 — Open the PCAP

### 1.1 Load and orient — expected answers

- **Frames matching `modbus` filter:** 296
- **TCP conversations:** 1
- **Source IP : port:** `172.20.10.4 : 43488` (the master, ephemeral high port)
- **Destination IP : port:** `172.20.10.3 : 502` (the slave, well-known)

### 1.2 Master vs slave

- **Master:** `172.20.10.4`
- **Slave:** `172.20.10.3`

Evidence students should cite:
1. The `:502` side is the *well-known* Modbus port — by IANA assignment,
   the server (slave) listens on it. The other side uses an ephemeral
   port (`43488`), the classic client-server signature.
2. The `:43488` side **initiates the TCP handshake** (`Statistics →
   Conversations → TCP → Relative Start`). Initiator = client = master
   in Modbus.
3. Every Modbus *request* (function code with zero data after) goes
   `:43488 → :502`; every *response* goes `:502 → :43488`.

> **Trap to watch for:** students who say "the slave is whichever IP is
> lower" or "the master is on .4 because 4 > 3". Push back hard —
> Modbus role is determined by **protocol behaviour**, not addresses.
> In a real plant the master can be a SCADA workstation, an HMI, or
> another PLC — its IP carries no semantic.

---

## Section 2 — Hand-decode the first frame

### 2.1 MBAP header (frame 1)

| Field | Value | Hex |
|---|---|---|
| Transaction Identifier | 17 | `00 11` |
| Protocol Identifier | 0 | `00 00` |
| Length | 6 | `00 06` |
| Unit Identifier | 1 | `01` |

**Transaction Identifier (why?)**
Even though TCP guarantees byte order, the MBAP transaction ID lets
a master pipeline multiple outstanding requests on the *same* TCP
connection and still pair each reply with its request — Modbus is a
request/response protocol, but TCP is just a byte stream, so without
a transaction ID the master couldn't tell which response belongs to
which request if it sent two in flight. It is also a holdover from
serial-line Modbus where multiplexing required explicit IDs.

**Protocol Identifier**
Always `0x0000` in Modbus TCP. Reserved by the spec for future
extensions that never materialised — `0` means "this is Modbus".
Treat any other value as malformed.

**Unit Identifier**
Holdover from **Modbus RTU / Modbus ASCII over RS-485**. On a serial
multi-drop bus, the unit ID identified *which slave on the wire* the
master was addressing. On TCP it is mostly cosmetic — usually `1`
when the IP itself uniquely identifies the device, or `255` ("any")
when the request is destined for a gateway that will forward to a
specific RTU slave behind it. Bridges between Modbus TCP and serial
buses use it.

---

### 2.2 PDU — request (frame 1)

- **Function code:** `3` → **Read Holding Registers**
- **Reference number / starting address:** `0`
- **Word count / quantity:** `15`

> Students may write "Read Holding Registers" *or* simply "read 15
> integers starting at register 0". Both are fine — the function code
> name is what they'd Google.

---

### 2.3 PDU — response (frame 2)

- **Function code:** `3` (echoed back — same code = success; a code
  with bit 7 set, e.g. `0x83`, would be an *exception response*)
- **Byte count:** `30`
- **Register count returned:** `30 / 2 = 15` ✓ matches request

---

### 2.4 Reconstruct the request

The 12 raw Modbus bytes on the wire for frame 1:

```
MBAP (7 bytes):  00 11   00 00   00 06   01
                 ^trans  ^proto  ^len    ^unit
PDU  (5 bytes):  03   00 00   00 0F
                 ^fn  ^start  ^count
```

- Total Modbus message length: **12 bytes** (7 MBAP + 5 PDU)
- MBAP Length field = 6, which counts **only what follows it**
  (unit ID + PDU = 1 + 5 = 6). ✓

> **Debrief point:** the Length field excluding itself is a classic
> source of off-by-one parser bugs — this is why malformed-length
> fuzzers find so many bugs in Modbus stacks.

---

## Section 3 — Statistics on the full capture

### 3.1 Function-code histogram

```
    296 3
```

**Only function code 3.** Every single Modbus frame in the capture is
either a Read Holding Registers request or its reply. No writes
(FC=6, 16), no diagnostic (FC=8), no read coils (FC=1), nothing.

> **What this means:** the master is purely *observing*. This is
> exactly what an HMI / data historian / SCADA poller does — read,
> read, read, never write. Writes only happen during setpoint changes
> or commissioning. A capture with FC=6 or FC=16 mixed in would
> indicate active control.

---

### 3.2 Register map

```
3   0   15
```

Just one unique tuple. The master polls **holding registers 0–14
inclusive** (a contiguous 15-register block), nothing else.

> **Why this matters for Module 3:** the attacker now knows
> *exactly* which registers are interesting. Anything outside 0–14
> the master doesn't read, so writes there will likely go unnoticed.
> Anything inside 0–14 the master will see on the very next poll.

---

### 3.3 Polling cadence

Expected output (counts may vary slightly):

```
1.19  ~13
1.20  ~77      ← mode
1.21  ~48
1.22  ~4
```

- **Most common interval:** ~1.20 s
- **Polls per minute:** ~50 (≈ 60/1.2)
- **Steady, not bursty** — variance is sub-30ms, all from scheduler
  jitter. This is the signature of an **automated polling loop**, not
  a human operator. A human clicking refresh would produce highly
  irregular gaps.

> **Debrief:** the cadence is the most reliable fingerprint of a
> SCADA poller. Defenders can baseline it once and alarm on any
> deviation — sudden bursts (= second master appeared), gaps (= master
> died), or new register addresses appearing (= attacker probing).

---

### 3.4 Response time

- **Typical latency:** ~0.4–5 ms (Docker bridge loopback)
- Tells you:
  - **(a)** The network is essentially zero-latency — master and slave
    are on the same L2 segment.
  - **(b)** The PLC is comfortably under-loaded. Real Allen-Bradley /
    Siemens PLCs answer in single-digit ms when idle; this matches.
    If response times started climbing, the PLC's CPU load or scan
    cycle is being affected — a known sign of either too many polls
    or active attack (Stuxnet-style register-flooding).

---

## Section 4 — Inferring the plant

### 4.1 Read the values

For the **shipped** capture, frame 2 returns:

| Register | Value (uint16) |
|---|---|
| 0 | 1665 |
| 7 | 1358 |
| 14 | 5279 |

(Values drift across the capture — the HAI replay walks through real
sensor data. Any plausible reading from frames 2–200 is fine.)

Students should observe:

- **Not random.** Consecutive polls produce values that are *close to
  each other but not identical* — frame 2 R0=1665, frame 5 R0
  probably 1664/1666/1670-ish. That's analog noise, not bitmask
  toggling.
- **Different magnitudes.** Some registers sit around 200-300, others
  around 800, others around 5000. That's a strong signal of **scaled
  engineering units** — different physical quantities (flow vs
  pressure vs level) measured in different units, sometimes with
  decimal scaling (e.g. register stores `pressure * 10`).
- **Always non-negative integers ≤ 65535.** Consistent with uint16
  registers. If they were floats they'd be split across two
  consecutive registers (Modbus has no native float type) — students
  who notice this and ask are operating at the right level.

---

### 4.2 What is this process? — model answer

> A continuous industrial process with 15 analog sensors being
> polled at ~50 Hz·min⁻¹ (every 1.2 s). The values are scaled
> engineering units in uint16 form — different registers have very
> different magnitudes (R0≈1600s, R7≈1300s, R8≈300, R14≈5000s),
> which is consistent with mixed sensor types — flow transmitters
> typically read 0–1000 L/min or 0–10000 (scaled ×10), pressure
> 0–100 bar (scaled ×100), tank levels 0–100%, valve positions
> 0–100. The 1.2 s update rate is too slow for safety interlocks
> (those run at 10–100 Hz in PLC firmware) but fast enough for an
> HMI / historian. No writes are seen, so this connection is
> *observation only*: a SCADA poller or data diode feeding a
> dashboard. The 15-register contiguous block is the entire useful
> state of one process unit — likely a single skid or treatment
> stage in a larger plant.

Strong students will also note:

- Different sensor magnitudes ⇒ probably mixed transmitter types ⇒
  this isn't a single-quantity process (e.g. not "15 thermocouples
  in one furnace"), it's a multi-variable process unit.
- 1.2 s × 15 registers = the cost of a full plant snapshot. Cheap.
  A real plant might have hundreds of registers; reading 15 means
  someone curated them as "the important ones".

> **Pedagogical point:** the student has reconstructed a plausible
> picture of the plant's physical reality *purely from network
> traffic patterns*. This is exactly what threat intel analysts do
> for unattributed ICS captures. The technique is real and useful.

---

## Section 5 — Security properties

### 5.1 What's missing — accept any three of

| Missing mechanism | How student knows |
|---|---|
| **Authentication** | No login, certificate, token, or challenge bytes in any frame; the master simply opens TCP/502 and starts reading. |
| **Encryption** | All Modbus PDU bytes are visible in cleartext in the hex pane — function codes, register addresses, register values. |
| **Integrity check beyond TCP checksum** | MBAP has *no* CRC, MAC, or signature; once an attacker injects a valid TCP segment, the slave will execute it. (Serial Modbus RTU does have a CRC-16; TCP Modbus dropped it because TCP "already checksums" — a flawed argument.) |
| **Replay protection** | Transaction IDs are sequential and predictable — an attacker can record a write and replay it later with no detection. |
| **Authorisation** | There's no concept of "this master may read regs 0–14 but not write reg 8". Any TCP-connected peer is a master and may issue any function code. |
| **Session / connection state** | The slave will happily accept commands from a *second* TCP connection on :502 with no challenge — there's no "one master at a time" lock. |
| **Audit log on the wire** | The slave doesn't broadcast "I just executed X for client Y" — accountability lives only in slave-side firmware logs, which most PLCs don't have. |

Accept any three of the above. **Push back** on "no firewall" (that's
a network control, not a protocol property) or "no antivirus"
(category error).

---

### 5.2 The attacker's checklist

> **One packet, function code 6, written to register 8** (chosen because
> 8 holds the smallest baseline value (~276) — likely a flag/setpoint
> rather than a sensor — so a forced write to a non-sensor register
> may go unnoticed if students target inside 0–14, but writing to
> registers *outside* 0–14 won't be polled by the master at all.)
>
> The honest answer: the master would notice on its next poll (1.2 s
> later) only if the write changes a register the master reads (0–14).
> If the attacker writes to register **100**, the master would never
> see it — the PLC would happily accept and store the value, and a
> physical effect would propagate to whatever logic uses register 100
> *with zero observability from this master*. That's the lesson.
>
> **Can the master tell the difference between "my own write" and
> "an attacker's write"?**
> **No.** Modbus carries no source-attribution. The master only sees
> values; it cannot distinguish "the value I set" from "the value
> someone else set". The only way to detect a rogue write is *out of
> band* — slave-side logs, a passive IDS watching FC=6/16 traffic
> from non-master IPs, or by anomaly on the physical process.

---

### 5.3 Real-world incidents — accept any of

- **Triton/Trisis (2017)** — though primarily TriStation, attackers
  used Modbus for lateral discovery in early stages.
- **"Industroyer / CrashOverride" (2016, Ukraine)** — payload module
  spoke IEC-101/104 + Modbus to issue malicious commands to grid
  substations; demonstrates the no-auth issue at country scale.
- **Modbus/TCP Security RFC** ([RFC 8516 draft, IETF](https://datatracker.ietf.org/doc/draft-dube-modbus-tcp-security/))
  — the formal vendor response: TLS + X.509 + role-based auth.
  Adoption: minimal.
- **ICS-CERT advisories** on register-write abuse against Schneider
  Modicon, Siemens S7-1200 Modbus libraries, AutomationDirect.
- **Project Basecamp (Digital Bond, 2012)** — published ~60 exploits
  against PLCs leveraging the no-auth design of Modbus.
- **"Boiling Frogs" (Wightman / Atredis, ICS Village DEF CON)** —
  live demos of forced register writes on water-treatment skids.

Reject **Stuxnet without specifics** (it used Profibus / S7, not
Modbus, in the attack payload — though it serves the same lesson).

---

## Debrief script (5 min, after the module)

Cover these three points:

1. **You just reverse-engineered a plant from 444 packets.** No
   docs, no creds, no internet. That's what Modbus's lack of
   confidentiality buys an attacker — and what a defender's IDS
   never had a chance to obscure. The protocol was designed in 1979
   for trusted serial buses; TCP gave it the internet without
   giving it security.

2. **The register map is now your weapon.** In Module 3 you will
   use the exact knowledge you extracted here — FC=03, registers
   0–14, unit ID 1 — to send your *own* requests. The defender's
   only hope is to notice that the requests are coming from the
   wrong source IP, because the protocol itself cannot tell.

3. **Cadence and function-code distribution are your defender's
   fingerprints.** A passive Modbus IDS doesn't need to decrypt
   anything; it baselines who polls what, how often, and which
   function codes are normal. Anomalies are loud. We'll do this in
   Module 4.
