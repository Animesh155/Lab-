# Module 5 — Protocol Diversity (S7comm + OPC UA)

**Duration:** ~40 minutes
**Prereqs:** Modules 1-4 (you know Modbus end-to-end now)
**You will produce:** a filled-in comparison table at the end of §3
plus two ~20-line clients you wrote yourself (one S7, one OPC UA).

> Same plant. Same diode pipeline. Same `attacker` shell. **Two new
> PLCs you haven't touched yet**: `plc-s7` speaking Siemens S7comm
> on TCP/102, and `plc-opcua` speaking OPC UA Binary on TCP/4840.
> Your job is to get to know them the way you got to know Modbus —
> but only on what's *different*.

---

## Lab environment

After `bash lab_protocols/provision.sh`, you have:

```bash
docker exec -it attacker bash
```

Inside the attacker container:

| Path | Contents |
|---|---|
| `/lab/pcaps/multi.pcap` | 30 s capture of all three protocols in use, captured during provision |
| `/lab/tools/attack.py` | Parametrized attack: `--protocol modbus\|s7\|opcua --tag N --value V` |
| `/lab/tools/browse_opcua.py` | Walks the OPC UA address space |
| `/lab/tools/subscribe_opcua.py` | Subscribes to one OPC UA variable and prints every update |
| `/lab/tools/your_s7_client.py` | Empty — **you write this in §1.3** |
| `/lab/tools/your_opcua_client.py` | Empty — **you write this in §2.2** |

All three PLCs are reachable on `ot-net`:

| Hostname | Protocol | Port |
|---|---|---|
| `plc-modbus` | Modbus TCP | 502 |
| `plc-s7` | Siemens S7comm | 102 |
| `plc-opcua` | OPC UA Binary | 4840 |

---

## §1 — S7comm: the protocol Stuxnet rode in on (20 min)

### §1.1 — Fingerprint (5 min)

Modbus told you "something is on port 502." See what S7 tells you.

```bash
nmap -p 102 --script s7-info plc-s7
```

> **Q1.1.a** — What does the `s7-info` script return that an `nmap
> -sV` against Modbus did *not*?
> _______________________________________________________________
>
> **Q1.1.b** — Why would a targeted attacker care about the module
> type, firmware version, and serial number?
> _______________________________________________________________

### §1.2 — Decode one frame (8 min)

The provision step captured a 30-second multi-protocol PCAP. Pull
one S7 Read Var frame out of it and annotate the byte layout:

```bash
tshark -r /lab/pcaps/multi.pcap -Y 's7comm' -V -c 1 | less
```

Map the headers you see to this structure (write the actual byte
values from your frame into the second column):

| Layer | Bytes |
|---|---|
| TPKT (4 bytes — magic, version, length) | `_______________________` |
| COTP (3 bytes — DT class for data) | `_______________________` |
| S7 PDU header (protocol byte, ROSCTR, …) | `_______________________` |
| Function code (1 byte: 0x04 = Read Var) | `_______________________` |
| Item count | `_______________________` |
| Item: addr type, area, DB number, start byte | `_______________________` |

> **Q1.2.a** — How many bytes total in your S7 Read Var request?
> _____ bytes.
>
> **Q1.2.b** — A Modbus FC=03 read request is **12 bytes**. Why is
> S7 ~2.5× larger for the same "give me a value" semantic? Did the
> extra bytes buy any security?
> _______________________________________________________________

### §1.3 — Write your own S7 client (7 min)

Open `/lab/tools/your_s7_client.py` and write a client that:
1. Connects to `plc-s7` (rack 0, slot 1)
2. Reads 30 bytes from DB1 starting at offset 0
3. Writes the value 9999 (big-endian uint16, `\x27\x0f`) into
   DB1.DBW0

Hint — your imports are:
```python
import snap7, socket
```

`snap7.client.Client()` is your entry point. Note: `libsnap7` does
**not** do DNS resolution, so you must `socket.gethostbyname()` the
hostname before calling `client.connect()`.

Run it:
```bash
python3 /lab/tools/your_s7_client.py
```

> **Q1.3.a** — Did the write succeed? What auth did you have to
> provide?
> _______________________________________________________________

After it works, ask your instructor about **Stuxnet**. The pattern
you just wrote — read DB, modify, write DB — is essentially the
attack vector at Natanz, hidden inside legitimate Step7 project
files. The protocol you just attacked is the headline ICS protocol
in the world's most famous cyber-physical attack.

---

## §2 — OPC UA: the protocol that finally has a security option (20 min)

### §2.1 — Browse the address space (5 min)

You do not need a register map for OPC UA. The server hands it
out for free.

```bash
python3 /lab/tools/browse_opcua.py
```

You'll see a tree of typed variables under `Objects/ProcessVariables/`.

> **Q2.1.a** — How does this change the attacker's job compared
> to Modbus and S7?
> _______________________________________________________________
>
> **Q2.1.b** — Pick any three variable names and write their full
> NodeId path (e.g. `ns=2;s=P1_PIT01_pressure_1`):
> 1. _____________________________________________________________
> 2. _____________________________________________________________
> 3. _____________________________________________________________

### §2.2 — Write your own OPC UA client (8 min)

Open `/lab/tools/your_opcua_client.py`. This time you don't write
a poller — you write a **subscriber**.

Adapt `/lab/tools/subscribe_opcua.py` (which you can read freely)
to subscribe to `ns=2;s=P1_PIT01_pressure_1` and print every
change for 30 seconds.

```bash
python3 /lab/tools/your_opcua_client.py
```

> **Q2.2.a** — Modbus and S7 are *poll* protocols. OPC UA can be
> *push*. Why does this matter for an OT network where some
> values change once a day and others 10 times a second?
> _______________________________________________________________
>
> **Q2.2.b** — The diode's `ot-proxy` polls every 1 second. What
> would have to change in the proxy if you wanted to carry
> event-driven OPC UA subscription semantics end-to-end through
> the diode?
> _______________________________________________________________

### §2.3 — Security flip (7 min)

First, run the attack with the OPC UA server in its **default**
(open) configuration:

```bash
python3 /lab/tools/attack.py --protocol opcua \
        --tag P1_TIT01_temperature_1 --value 99.9
```

> **Q2.3.a** — Did the write succeed? Auth provided?
> _______________________________________________________________

Now flip the server to secure mode. From the **host** (not inside
attacker):

```bash
bash lab_protocols/opcua-secure/up.sh
```

The script restarts `plc-opcua` with `Basic256Sha256` + cert auth.
Wait ~10 seconds, then re-run the same attack:

```bash
python3 /lab/tools/attack.py --protocol opcua \
        --tag P1_TIT01_temperature_1 --value 99.9
```

> **Q2.3.b** — What error did the attack return this time? Where
> in the OPC UA handshake did it fail? (Hint: the error message
> includes a phrase about `endpoints` — what's being negotiated
> when the rejection happens?)
> _______________________________________________________________
>
> **Q2.3.c** — Could you write a Snort rule that would have caught
> the original attack against the *open* server? Could you write
> one that catches it against the *secure* server? Why or why not?
> _______________________________________________________________

When you're done, return the server to default mode:

```bash
bash lab_protocols/opcua-secure/down.sh
```

---

## §3 — Synthesis: fill in the table (10 min)

Pull everything together. Use your own notes, your captured PCAP,
and the code you wrote.

| | Modbus | S7comm | OPC UA |
|---|---|---|---|
| Default port | 502 | _____ | _____ |
| Bytes to read 1 tag | 12 | _____ | varies |
| Setup handshake | none | _____ | _____ |
| Can browse the address space? | ❌ | _____ | _____ |
| Polling model | poll only | _____ | _____ |
| Default auth in this lab | none | _____ | _____ |
| Auth available if configured? | _____ | _____ | _____ |
| Famous breach you should know about | _____ | _____ | _____ |

> **Q3.a** — Of the three protocols, which one(s) gave you the
> *option* to stop the attack at the protocol layer? Which
> one(s) did not? Why?
> _______________________________________________________________
>
> **Q3.b** — Complete this sentence in your own words: "Protocol
> modernity bought one thing — ________________________________
> ________________________________________________________________
> ________________________________________________________________."

---

## §4 — Submit

Push your two clients and your filled-in table to the instructor.

What to submit:
- `/lab/tools/your_s7_client.py`
- `/lab/tools/your_opcua_client.py`
- The filled-in comparison table from §3
- Written answers to all `Q` prompts

## Takeaway

You walked in knowing one ICS protocol. You walk out with three —
and more importantly, with a mental model of *why* each one is
the way it is. The diode pipeline didn't change between modules
1-4 and module 5: only the adapter changed. **Protocol diversity
is an adapter-layer concern, not an architecture concern.**

And the one sentence the whole module was engineered to make you
say without prompting: *protocol modernity bought one thing — the
option to authenticate. Whether anyone uses that option is an
operator decision, not a protocol decision.*
