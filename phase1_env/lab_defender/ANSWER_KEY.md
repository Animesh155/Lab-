# Module 4 — Answer Key
### The Defender's View (Zeek + Snort)

> Instructor reference. Every numeric value below comes from
> running the task-sheet commands against the shipped
> `pcaps/attack.pcap` (271 packets, 88 seconds, captured on
> `plc-modbus:eth0` while Module 3's attack was executed
> end-to-end).

---

## §1 — Get oriented

| Question | Expected answer |
|---|---|
| Packet count | **271** |
| Capture window | ~88 seconds (`Start time: 2026-06-18 10:50:46`, `End time: 2026-06-18 10:52:14`) |
| TCP conversations on :502 | **5** (one ~88-second long-lived from `172.20.10.4:*`, plus four short bursts from `172.20.10.10:*`) |

Why is the conversation count suspicious vs Module 2?
Module 2's baseline pcap had **one** long-lived TCP session — a
master holds the connection open for the lifetime of its polling
loop. Five conversations on a wire that should have one
master-slave pair is the first red flag.

---

## §2 — Decode with Zeek

### 2.1 Generated logs

After `zeek -C -r /lab/pcaps/attack.pcap /lab/zeek/load.zeek`:

```
conn.log              ~1.2 kB    5 connection records
modbus.log            ~17 kB     162 request+response pairs
modbus_detailed.log   ~16 kB     162 rows, with addr/qty/values
packet_filter.log     small      run metadata
```

### 2.2 — Q2.a — Master IP enumeration

```
$ awk '/^[^#]/' modbus.log | awk '{print $3}' | sort -u
172.20.10.10
172.20.10.4
```

**Two distinct master IPs.** The legit one is `172.20.10.4`
because that's what the Module 1 nmap recon showed as the
diode ingress proxy (ot-proxy), and the Module 2 PCAP confirmed
that IP as the persistent polling master. **`172.20.10.10` is
unknown to the topology** — students who completed Module 3
will recognise it as the engineering-ws pivot host.

### 2.3 — Q2.b — Function-code profile per master

```
$ awk '/^[^#]/' modbus.log | awk '{print $3, $9}' \
   | sort | uniq -c | sort -rn
    148 172.20.10.4   READ_HOLDING_REGISTERS     ← legit (req+resp)
      8 172.20.10.10  READ_HOLDING_REGISTERS     ← rogue (req+resp)
      6 172.20.10.10  WRITE_SINGLE_REGISTER      ← rogue (req+resp)
```

(`modbus.log` logs both REQ and RESP rows, hence the doubling.)

- **Legit master** (`172.20.10.4`): only ever issues
  `READ_HOLDING_REGISTERS`. Reads are pure observation — they
  cannot change plant state. The fact that the legit polling
  loop is *read-only* is itself an architectural property: the
  HMI's data flow is one-way (PLC → InfluxDB), the ot-proxy
  never needs to write. This is what makes write-anywhere
  detection rules viable.
- **Rogue master** (`172.20.10.10`): mix of 4 reads and 3
  writes. The reads alone are arguably reconnaissance (`read 0
  15`), the writes are the actual impact.

### 2.4 — Q2.c — Writes in detail

```
$ awk -F'\t' '/^[^#]/ && $9 ~ /WRITE/ {
    print $3, $9, "addr="$10, "val="$12
}' modbus_detailed.log
172.20.10.10 WRITE_SINGLE_REGISTER addr=5   val=9999
172.20.10.10 WRITE_SINGLE_REGISTER addr=100 val=42
172.20.10.10 WRITE_SINGLE_REGISTER addr=500 val=1
```

Cross-referencing against the Module 2 baseline:

| addr | Polled by legit master? | Effect of write |
|---|---|---|
| 5   | **Yes** (regs 0-14) | Visible 1 Hz "flicker" — next legit poll overwrites it back to the normal value |
| 100 | **No**              | Invisible; the SCADA never reads register 100 |
| 500 | **No**              | Invisible; same reason |

This is the Module 3 lesson, now visible from the network side:
the rogue master left fingerprints in `modbus_detailed.log` for
**all three** writes, even the two the SCADA dashboard never
showed.

### 2.5 — Q2.d — Detection rule sketch

Expected sentence-level answers (in increasing sophistication):

1. *"Alert on any Modbus traffic to `172.20.10.3:502` from a
   source IP that is not `172.20.10.4`."* — the source-IP
   allow-list. Simple and high-value.
2. *"Alert on any function code 0x06 (Write Single Register)
   destined for the PLC."* — writes are rare and consequential;
   alerting on all of them is cheap.
3. *"Alert on any FC=06 to register address ≥ 15, since the
   master only polls registers 0-14."* — the "invisible write"
   detector. Bonus.

Any of the three earns credit. Strong students will articulate
how each rule trades off coverage vs false-positive rate.

---

## §3 — Snort with empty rules

```
$ snort -r /lab/pcaps/attack.pcap -c /lab/snort/snort.conf \
        -A console -q -k none | grep -c Priority
0
```

**Q3 — Why zero alerts?** Because Snort is a *signature* engine —
it matches packets against rules. With `local.rules` empty, no
rules exist, so nothing matches. Zeek, in contrast, is a
protocol *parser* — it produces logs unconditionally for
everything it understands. The distinction is the central
trade-off of network monitoring:

- Zeek: passive, always-on, expensive to store, gives you
  evidence after the fact.
- Snort: cheap, real-time, but only sees what you told it to
  look for.

A mature SOC runs both, and uses Zeek's logs to write new Snort
rules.

---

## §4 — Student-authored rule

### 4.3 — Expected solutions

See `/lab/snort/example.rules` for the reference set. The three
"good answer" rules and their alert counts on the shipped pcap:

| Rule | Idea | Alerts on shipped pcap |
|---|---|---|
| **R1** | Alert TCP from `!172.20.10.4` to PLC:502 | **22** |
| **R2** | Alert on byte 7 of payload == 0x06 (FC=06)  | **3** |
| **R3** | R2 plus `byte_test:2,>=,15,0,relative,big` (addr ≥ 15) | **2** |

To verify against the instructor reference:

```bash
sudo docker exec defender-tools bash -c '
  cp /lab/snort/snort.conf /tmp/snort.conf
  sed -i "s|local.rules|example.rules|g" /tmp/snort.conf
  snort -r /lab/pcaps/attack.pcap -c /tmp/snort.conf \
        -A console -q -k none \
    | grep -oE "OT-IDS R[0-9]" | sort | uniq -c'
```

Expected output:

```
     22 OT-IDS R1
      3 OT-IDS R2
      2 OT-IDS R3
```

(R3 = 2 alerts because it fires on the writes to registers 100
and 500, NOT on the write to register 5. This is the high-fidelity
"invisible write" detector.)

### 4.4 — Bonus rule discussion

R1 is the rule a student is most likely to write first. It's
also the rule that an attacker spoofing the legit master's IP
would completely defeat. R2 is the "we don't trust source IPs"
fallback, and a sophisticated student will notice that R2
catches the writes regardless of source.

R3 is the "Stuxnet-style" detector — it alerts on writes to
memory the SCADA never reads, which is by definition where
stealth attacks land. Pair it with R2 and you get both the
loud and the stealthy attacks.

### Common mistakes & coaching

- **Forgetting `flow:to_server,established;`**: rule fires on
  responses too, generating duplicate alerts and looking
  symmetric in the output. Coach: "the response goes the other
  way; you want client-to-server only."
- **`content:"\x06"; offset:7;`** (no pipe wrapper): Snort 2.9
  treats this as the literal three-character string `\x06`.
  Pipe-wrapped hex (`|06|`) is the correct form.
- **`depth:1` missing**: rule still works, but Snort searches
  the rest of the payload looking for any 0x06 byte, which can
  fire on data bytes that happen to be 0x06 (e.g., the value
  field of a write). Coach: "anchor it; you know the exact
  position."

---

## §5 — What the rule misses

### Q5.a — When R1 produces zero alerts

> The attacker has already compromised `172.20.10.4` (the
> ot-proxy itself), or is physically on the OT switch and can
> source-spoof. Either way, malicious writes now come *from*
> the allowed IP. R1 — by construction — gives zero alerts.

This is the structural limit of source-IP allow-listing in
flat OT networks: it presumes the host identity hasn't been
forged or compromised, but the same low-protection assumptions
that made OT networks attractive targets in the first place
(no auth, no certificates, no host attestation) also make IP
trust meaningless.

Real-world analogue: the **Ukraine 2015 / 2016** grid attacks
used legitimately-credentialed HMI sessions to issue malicious
breaker commands. An R1-style detection would have produced
zero alerts.

### Q5.b — R2 false-positive analysis

> R2 alerts on every FC=06. In a real plant, operators
> legitimately change setpoints throughout the day — flow
> targets, alarm thresholds, batch parameters. A plant that
> changes 20 setpoints per shift × 3 shifts × 30 days = ~1800
> alerts/month from R2 alone. Almost all of them benign.

Tuning options (any of these is acceptable):

1. **Time-of-day**: legitimate setpoint changes happen during
   shift hours. An R2 alert at 02:30 is much more suspicious
   than one at 14:00.
2. **Source-IP enrichment**: combine R2 with R1 — alert only
   on FC=06 *from non-HMI hosts*. (HMI source IP becomes the
   allow-list.)
3. **Rate-limit**: alert on FC=06 only when more than N writes
   per minute (Stuxnet's payload bursts were rapid; operator
   actions are slow). This is what Snort's `threshold` keyword
   does.
4. **Specific-register allow-list**: define which registers
   operators are allowed to write to, alert on the rest. (R3 is
   a coarse version of this.)

Strong students will note that **operator behaviour itself
becomes the signal** — anything that doesn't match the operator
profile is anomalous. This is the gateway to behavioural ICS
detection (Dragos, Nozomi, Claroty all do this).

### Q5.c — Read-only reconnaissance

> A bare `read 100 1` produces **no Snort alert** (none of R1,
> R2, R3 would fire — wait, R1 *would* fire because R1 is
> source-IP based, not function-code based.)
>
> So the correct answer depends on which rules the student wrote:
> - If they wrote R1 (source-IP): **Snort catches it**.
> - If they wrote only R2 / R3 (FC=06-based): **Snort misses
>   it** — reads aren't writes.
>
> Zeek catches it either way: `modbus_detailed.log` has a row
> for every Modbus operation, read or write. The defender
> investigating "all activity from `172.20.10.10`" would find
> the recon read immediately.

This is the second pedagogical point of §5: **Snort is what you
deploy live; Zeek is what saves you when Snort misses.** The
analyst's daily workflow is "Snort flagged this; pivot to the
Zeek logs to understand context".

---

## Instructor debrief (5 min, optional)

Three high-impact points to make verbally:

1. **The detection asymmetry is real.** A rogue master that
   issues even one Modbus packet is exposed because Modbus has
   no authentication — anybody can be the master. The same
   no-auth property that makes the attack trivial in Module 3
   is what makes the detection trivial in Module 4. There's no
   free lunch on either side.

2. **Signature vs anomaly is a deployment choice, not a
   "which is better" question.** R1 is a signature — it
   encodes "I know what bad looks like" (any IP that isn't the
   master). R2 is closer to an anomaly indicator (any write at
   all is suspicious in a read-only environment). Production
   ICS networks need both, and the human SOC analyst is the
   bridge.

3. **The diode didn't help.** Modules 1-3 built up a
   one-way IT/OT boundary, and the attack still succeeded —
   because it happened *inside* the OT side, between the
   engineering workstation and the PLC. The same attack
   reaches the same registers whether the diode is there or
   not. **The diode protects against IT→OT, not OT→OT.** The
   detection rules in Module 4 are the defender's response to
   that gap.

---

## Expected lab state

After `bash lab_defender/provision.sh`:

| IP | Container | Role |
|---|---|---|
| (no network) | `defender-tools` | analysis container — no network needed |
| Mounted: `/lab/pcaps/attack.pcap` | the shipped capture |
| Mounted: `/lab/snort/local.rules` | rw, student-editable |
| Mounted: `/lab/snort/snort.conf`  | ro, includes `local.rules` |
| Mounted: `/lab/zeek/load.zeek`    | ro, icsnpp-modbus loader |

This module **does not require** the base diode stack or the
lab_exploit overlay to be running. The shipped pcap is the
only input; everything is offline analysis. That makes Module
4 the most portable of the four — you can hand a student the
defender-tools image + pcap on a USB stick and they can do the
whole module on a disconnected laptop.
