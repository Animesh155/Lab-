# Module 2 — Protocol Fingerprinting (Modbus Deep-Dive)

> **Time:** 60 minutes
> **Submit:** This sheet (with your answers) at the end of the module.
> **Tools:** `wireshark` (GUI on your VM), `tshark` (CLI inside the
> attacker container), `python3` + `pymodbus` (already installed).
> The PCAP file is at `/lab/pcaps/modbus-baseline.pcapng` inside the
> attacker container.
> **No internet** — the goal is to learn to *read* the protocol, not
> Google it.

---

## Your situation

In Module 1 you discovered that port 502 was unreachable from your
foothold. You also saw that the `ot-proxy` host on `172.20.10.4`
*does* talk to `plc-modbus` on `172.20.10.3:502` constantly. You
could not reach it, but a colleague on the OT-side support team
captured **3 minutes of that traffic** for you (`modbus-baseline.pcapng`,
444 packets) and dropped it on your foothold.

You have never read Modbus before. Your job in the next hour is to
decode it well enough to answer four questions:

1. **What is the master doing?** (function code, register range, rate)
2. **What is the slave?** (one PLC? many? what unit IDs?)
3. **What does the physical process look like?** (inferred from the
   register map alone)
4. **What could go wrong?** (security properties of the protocol)

You will hand-decode the first frames in Wireshark, then use `tshark`
to extract statistics from the full capture, then write a one-paragraph
inference about the plant.

---

## Section 1 — Open the PCAP (5 min)

### 1.1 Load and orient

Open the file in Wireshark (`File → Open`, navigate to the PCAP, or
launch `wireshark /lab/pcaps/modbus-baseline.pcapng` from a terminal).
Apply the display filter:

```
modbus
```

> _How many frames match the `modbus` filter?_  ________________
>
> _How many TCP conversations are in the capture?_
> (Hint: `Statistics → Conversations → TCP`)  __________________
>
> _Source IP : port_     ______________________________________
> _Destination IP : port_ _____________________________________

---

### 1.2 Master vs slave — figure it out from the conversation

> **Which IP do you think is the Modbus master, and which is the
> slave?** Justify from what you see — *not from the IP address*.
>
> (Hint: think about which side initiates, which port is "well-known",
> and which side sends requests vs responses.)
>
> _Master:_ __________________  _Slave:_ ___________________
>
> _Why (2 sentences):_
> ______________________________________________________________
> ______________________________________________________________

---

## Section 2 — Hand-decode the first frame (15 min)

Click **frame 1** in Wireshark. In the middle pane, expand:
`Modbus/TCP` then `Modbus`.

You are looking at the **MBAP header** (Modbus Application Protocol
header, 7 bytes) followed by the **PDU** (Protocol Data Unit).

### 2.1 The MBAP header

Fill in the field values from frame 1:

| Field | Bytes | Value |
|---|---|---|
| Transaction Identifier | 2 |  |
| Protocol Identifier | 2 |  |
| Length | 2 |  |
| Unit Identifier | 1 |  |

> _What does the **Transaction Identifier** do? Why do you think
> Modbus has one if the underlying transport is TCP (which already
> orders bytes)?_
>
> ______________________________________________________________
> ______________________________________________________________

> _What is the **Protocol Identifier** field always set to in Modbus
> TCP, and what is it there for?_
>
> ______________________________________________________________

> _The **Unit Identifier** is a holdover from a previous transport.
> Which one? What was its original purpose?_  (One sentence.)
>
> ______________________________________________________________

---

### 2.2 The PDU — request

Still on frame 1, look at the **Modbus** sub-tree:

> _Function code (decimal):_ ______
>
> _Function name (what does this code mean — your best guess
> from the field labels):_  ____________________________________
>
> _Reference number / starting address:_  ______
>
> _Word count / quantity of registers:_  ______

---

### 2.3 The PDU — response

Click **frame 2** (the reply). Same expansion.

> _Function code:_  ______   _Byte count:_ ______
>
> _If each register holds a 16-bit value, how many registers worth
> of data did the slave just return? Does that match what frame 1
> requested?_
>
> ______________________________________________________________

---

### 2.4 Reconstruct the request/response by hand

Switch Wireshark's bottom pane to **Hex view**. Find the Modbus
payload bytes for frame 1. Write them out:

```
MBAP (7 bytes):  __ __  __ __  __ __  __
PDU  (5 bytes):  __  __ __  __ __
                 ^   ^      ^
                 fn  start  count
```

> _Total Modbus message length on the wire:_  ______ bytes
> _Does the "Length" field in MBAP match?_  Y / N

---

## Section 3 — Statistics on the full capture (15 min)

Switch to `tshark` for the bulk work. Inside the attacker container:

```bash
cd /lab/pcaps
```

### 3.1 Function-code histogram

```bash
tshark -r modbus-baseline.pcapng -Y "modbus" \
       -T fields -e modbus.func_code | sort | uniq -c
```

> _Output:_
> ______________________________________________________________

> _What does this tell you about what kind of operation the master
> is performing? Reads, writes, both?_
>
> ______________________________________________________________

---

### 3.2 Register map

```bash
tshark -r modbus-baseline.pcapng -Y "modbus and tcp.dstport==502" \
       -T fields -e modbus.func_code -e modbus.reference_num \
                 -e modbus.word_cnt | sort -u
```

> _Unique (function, start, count) tuples observed:_
> ______________________________________________________________

> _Which contiguous block of registers is the master polling?
> Express as a range._  ________________________________________

---

### 3.3 Polling cadence

```bash
tshark -r modbus-baseline.pcapng -Y "modbus and tcp.dstport==502" \
       -T fields -e frame.time_relative \
  | awk 'NR==1{p=$1;next}{printf "%.2f\n",$1-p;p=$1}' \
  | sort -n | uniq -c
```

> _Most common inter-request interval:_  ____ s
>
> _Polls per minute:_  ______
>
> _Is the cadence steady or bursty? What does that imply about
> whether this is a human operator or an automated process?_
>
> ______________________________________________________________

---

### 3.4 Response time

```bash
tshark -r modbus-baseline.pcapng -Y "modbus" \
       -T fields -e frame.time_relative -e mbtcp.trans_id \
                 -e tcp.dstport \
  | head -20
```

Pair up request (dstport 502) and response (srcport 502) by
transaction ID and compute the latency.

> _Typical request-to-response latency:_  ______ ms
>
> _What does that tell you about (a) the network between master and
> slave, (b) the PLC's responsiveness?_
>
> ______________________________________________________________

---

## Section 4 — Inferring the plant (15 min)

You now know **exactly** what the master is asking for: a contiguous
block of holding registers, polled at a steady rate, no writes, no
diagnostics. That's enough to reason about the physical process.

### 4.1 Read the values

Look at the **response payload** in Wireshark for any one frame
(e.g. frame 2). The byte_count tells you how many bytes follow;
each pair of bytes is one register value (big-endian uint16).

Pick 3 register values from the response and write them as
decimal:

```
Register 0 (the first):   ____________
Register 7 (middle-ish):  ____________
Register 14 (last):       ____________
```

> _Do the values look like raw integers, scaled engineering units,
> bitmasks, or something else? What's your evidence?_
>
> ______________________________________________________________
> ______________________________________________________________

---

### 4.2 What is this process?

You're now allowed to make a **one-paragraph inference** about what
the plant actually does. Use only what you've extracted from the
PCAP — no internet, no Module 1 notes.

> _What kind of plant is this? How many physical signals are being
> monitored? What's the process update rate? Why might one register
> hold a value of ~165 while another holds ~825 — what physical
> quantity could each represent? Be specific._
>
> ______________________________________________________________
> ______________________________________________________________
> ______________________________________________________________
> ______________________________________________________________
> ______________________________________________________________

---

## Section 5 — Security properties (10 min)

> **Internet allowed for this section only.**

Modbus was designed in **1979** by Modicon (now Schneider Electric)
for serial communication between PLCs. Modbus TCP just wraps the
same PDU in a TCP frame.

### 5.1 What's missing?

You have read 296 Modbus frames. Without consulting the spec, name
**three security mechanisms that are absent** from what you saw on
the wire.

| # | Missing security mechanism | How you'd know it's absent |
|---|---|---|
| 1 |   |   |
| 2 |   |   |
| 3 |   |   |

---

### 5.2 The attacker's checklist

You will attack this network in Module 3. Based on what you now
know about Modbus:

> _If you could send **one** Modbus packet to this PLC, what
> function code would you use, and what would you do with it?_
> (Hint: function code 6 is "Write Single Register".)
>
> ______________________________________________________________
> ______________________________________________________________

> _How would the master notice that something other than itself
> wrote a register? (Be honest. Could it?)_
>
> ______________________________________________________________

---

### 5.3 Real-world

Find **one documented incident** where Modbus's lack of authentication
was exploited (or where a vendor's "secure Modbus" variant — like
Modbus/TCP Security RFC, or Schneider's Modicon Security — was
proposed in response). Cite it (one URL or paper) and summarise
in **two sentences**.

```
Citation:  __________________________________________________

Summary:
________________________________________________________________
________________________________________________________________
```

---

## End of Module 2

Hand this in. In Module 3 you will get onto `ot-net` (two paths are
available — pick one) and use everything you just learned to send
your own Modbus packet to this PLC. Bring this worksheet — you'll
need the register map.
