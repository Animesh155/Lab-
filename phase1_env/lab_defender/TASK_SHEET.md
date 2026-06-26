# Module 4 — The Defender's View
### Zeek, Snort, and writing your first ICS detection rule

**Duration:** ~50 min
**Prereqs:** Modules 1 — 3 (you can do this module standalone if
needed; the shipped attack PCAP contains all the traffic from
Module 3).
**You will produce:** a working `local.rules` file with at least
one rule that detects the Module 3 attack, plus brief written
answers to the questions in §2 and §5.

> Module 3 ended with the attacker writing to PLC registers from
> a pivot host **and nothing being on fire — yet**. The plant
> didn't crash. The SCADA dashboards didn't blink. The legitimate
> master kept polling. The writes that hit registers 100 and 500
> are still there.
>
> Now you switch hats. **You are the defender.** Your SOC has
> captured 88 seconds of `ot-net` traffic that includes the
> attack. Your job is to find it.

---

## Lab environment

A single container, `defender-tools`, is running with **Zeek 8**,
**Snort 2.9**, **tshark**, and the **CISA icsnpp-modbus** parser
pre-installed.

```bash
docker exec -it defender-tools bash
```

Inside the container:

| Path | Contents |
|---|---|
| `/lab/pcaps/attack.pcap` | 271-packet capture of `ot-net` — read-only |
| `/lab/zeek/load.zeek`    | Pre-baked Zeek loader (loads icsnpp-modbus) |
| `/lab/snort/snort.conf`  | Minimal Snort config — already includes `local.rules` |
| `/lab/snort/local.rules` | **Your** rule file. Starts empty. Edit this in §4. |
| `/lab/work/`             | Scratch dir — Zeek writes its `.log` files here |

The pcap is the *only* input. **Nothing else is live.** This is
deliberate — you are reproducing what a real SOC analyst does
when handed a packet capture and asked "did anything bad
happen on this segment last weekend?"

---

## §1 — Get oriented (5 min)

Open a shell in `defender-tools` and answer these from the pcap
alone, no Zeek/Snort yet:

1. How many packets total?
   ```bash
   capinfos -c /lab/pcaps/attack.pcap
   ```

2. How long is the capture window?
   ```bash
   capinfos -uae /lab/pcaps/attack.pcap
   ```

3. How many distinct TCP conversations touch port 502?
   ```bash
   tshark -r /lab/pcaps/attack.pcap -q -z conv,tcp 2>/dev/null \
     | grep ':502'
   ```

   **Write down:** number of conversations, and what's
   suspicious about the row count compared to Module 2's
   baseline pcap.

---

## §2 — Decode with Zeek (15 min)

### 2.1 Run Zeek against the pcap

```bash
cd /lab/work
zeek -C -r /lab/pcaps/attack.pcap /lab/zeek/load.zeek
ls -la
```

You should see at least:
- `conn.log` — every TCP/UDP connection
- `modbus.log` — every Modbus request and response
- `modbus_detailed.log` — same, plus register addresses, values,
  and operation details (this is the icsnpp-modbus extension)

### 2.2 Identify every Modbus master

The legit master in Module 1's `nmap` was `172.20.10.4`
(ot-proxy). Were there others on this wire?

```bash
# Strip Zeek headers, take the source IP column from modbus.log,
# uniq it
awk '/^[^#]/' modbus.log | awk '{print $3}' | sort -u
```

> **Q2.a — How many unique Modbus master IPs talked to the PLC?
> Which one is legitimate, and how do you know?**

### 2.3 What function codes did each master use?

```bash
# request-only rows (response rows have func code too, both count)
awk '/^[^#]/' modbus.log | awk '{print $3, $9}' \
   | sort | uniq -c | sort -rn
```

> **Q2.b — Which function codes did the legit master use? Which
> did the rogue master use? Why is the *legit* master's function-
> code profile inherently safer?**

### 2.4 Pull out every write (FC=06) with the register address

icsnpp-modbus puts the address and value in `modbus_detailed.log`.

```bash
# Show source IP, function name, register address, request value
awk -F'\t' '/^[^#]/ && $9 ~ /WRITE/ {
    print $3, $9, "addr="$10, "val="$12
}' modbus_detailed.log
```

> **Q2.c — How many writes happened? Which register was written
> by which IP, and to what value? Cross-reference with the
> Module 2 baseline: was *any* of these registers ever polled by
> the legit master?**

### 2.5 The detection insight

> **Q2.d — Write one sentence describing the detection rule you
> could build with what you've learned. (Hint: it doesn't have
> to be clever. Simple is good.)**

---

## §3 — Run Snort with no rules (5 min)

```bash
snort -r /lab/pcaps/attack.pcap \
      -c /lab/snort/snort.conf \
      -A console -q -k none \
   | grep -c Priority
```

You should see **0**.

> **Q3 — Snort just ate 271 attack packets and produced zero
> alerts. Why? What's the difference between Snort and Zeek
> here?**

(Hint: the Module 2 worksheet's debrief about *passive vs
detection* is exactly what's biting you. Zeek logs what
happened; Snort matches on rules you give it.)

---

## §4 — Write your own rule (20 min)

Your goal: open `/lab/snort/local.rules` and add a rule that
fires on the attack but NOT on the legitimate poller.

### 4.1 The Modbus byte layout (refresher from Module 2)

Inside the TCP payload of a Modbus/TCP frame:

```
byte 0-1   Transaction ID
byte 2-3   Protocol ID (always 0x0000)
byte 4-5   Length
byte 6     Unit ID
byte 7     Function code      ← 0x03 = Read, 0x06 = Write Single Reg
byte 8-9   Reference number   ← register address (big-endian uint16)
byte 10-11 Value (for FC=06)
```

### 4.2 Snort 2.9 rule syntax — the parts you need

```
alert tcp <src_ip> <sport> -> <dst_ip> <dport> ( \
    msg:"<message>"; \
    flow:to_server,established; \
    content:"|XX|"; offset:N; depth:1;  ← match byte N == 0xXX
    sid:1000001; rev:1; )
```

Useful options:
- `![1.2.3.4]` — *NOT* this IP (note the leading `!`)
- `byte_test:2,>=,15,0,relative,big;` — read 2 bytes starting
  at offset 0 from the end of the last content match, big-endian,
  and trigger when value ≥ 15
- `sid` must be ≥ `1000000` for local rules

### 4.3 Your task

Write at least **one** rule that:

- Fires on every rogue master frame, AND
- Does NOT fire on any legit master frame

Test it after each edit:

```bash
snort -r /lab/pcaps/attack.pcap \
      -c /lab/snort/snort.conf \
      -A console -q -k none
```

> **Acceptance criteria:** at least one `[**] [sid:...]` line
> per rogue session, and zero alerts attributable to packets
> with source IP `172.20.10.4`. Verify:
>
> ```bash
> snort -r /lab/pcaps/attack.pcap -c /lab/snort/snort.conf \
>       -A console -q -k none \
>   | grep -E "172\.20\.10\.4" | wc -l
> # should be 0
> ```

### 4.4 Bonus rules (if time)

If your first rule was source-IP based: write a second rule
that doesn't rely on the source IP at all (because in the next
attack scenario, the attacker spoofs it).

If your second rule was function-code based: write a third rule
that fires only on writes to a register the SCADA never polls.

---

## §5 — What does your rule miss? (5 min)

> **Q5.a — Your IP-allow-list rule (R1-style) catches today's
> attack. Sketch one attack scenario in the same plant where R1
> would produce **zero alerts** even though malicious writes
> happened.**

> **Q5.b — Your FC=06 rule (R2-style) catches every write. What
> false-positive rate would you expect if you deployed it for a
> month in a *real* plant where operators legitimately change
> setpoints from the HMI? How would you tune the rule to keep
> the signal but cut the noise?**

> **Q5.c — Suppose the rogue master had run `read 100 1` and
> then *stopped* (the attacker just wanted to know if the
> register existed; no writes, no escalation). Which of Zeek
> and Snort would still have caught it, and using what
> evidence?**

---

## §6 — Submit

Push your `local.rules` and your written answers to the
instructor. Successful runs of:

```bash
snort -r /lab/pcaps/attack.pcap \
      -c /lab/snort/snort.conf \
      -A console -q -k none
```

…should produce at least one alert per rogue session AND zero
alerts whose source IP is `172.20.10.4`.

---

## Things to take away

This module is the answer to a question Module 3 quietly raised:
**did the diode help at all?** The diode itself didn't catch
the attack — the attack happened *upstream* of the diode, inside
the trusted OT segment. But the same physical and protocol
property that motivated the diode (one-way, no auth, no
attribution) is the same property that makes the detection rule
above so cheap to write.

In the real world, this is *exactly* the trade-off ICS defenders
work with: cheap, brittle, content-aware signature rules at the
network edge, plus passive logging tools like Zeek for forensic
investigation when the signature rules eventually fail.
