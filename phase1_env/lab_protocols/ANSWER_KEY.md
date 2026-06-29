# Module 5 — Answer Key (Protocol Diversity)

> Instructor reference. DO NOT show students. Every numeric value
> below comes from running the task-sheet commands against the
> shipped lab stack with all three PLCs (`plc-modbus`, `plc-s7`,
> `plc-opcua`) running in default configuration.

---

## §1 — S7comm

### §1.1 — Fingerprint

**Q1.1.a expected output of `nmap -p 102 --script s7-info plc-s7`:**

```
PORT    STATE SERVICE
102/tcp open  iso-tsap
| s7-info:
|   Module: 6ES7 ...
|   Basic Hardware: ...
|   Version: <firmware>
|   System Name: SNAP7-SERVER
|   Module Type: <type>
|   Serial Number: ...
|   Plant Identification: ...
|_  Copyright: Original Siemens Equipment
```

The exact values depend on snap7's defaults; what matters is that
**S7 returns a richly populated identification block**, whereas
Modbus on port 502 returns only "tcp open" with no service banner.

**Q1.1.b — Why the attacker cares:** firmware version → known CVE
mapping (e.g. PLC-Blaster wormable bugs targeted specific 1500
firmware ranges). Module type → which Step7 project structure to
assume. Serial → uniqueness fingerprint for tracking across scans.

### §1.2 — Decode

**Q1.2.a — Byte count:** S7 Read Var requests are 31 bytes. With
TPKT and COTP overhead they're consistently 2-3× larger than the
Modbus equivalent.

**Q1.2.b — Why bigger ≠ securer:** the extra bytes encode framing
hierarchy (TPKT for length-prefixed sessions over TCP, COTP for
OSI-style transport classes Siemens inherited from their MMS
heritage). None of those bytes carry auth tokens, integrity tags,
or sequence numbers that an attacker would have to forge. Both
protocols are zero-auth.

### §1.3 — Write your own S7 client

**Expected solution (your_s7_client.py):**

```python
import snap7
import socket

HOST = "plc-s7"
ip = socket.gethostbyname(HOST)

c = snap7.client.Client()
c.connect(ip, 0, 1)              # rack 0, slot 1 = S7-1200/1500 default
assert c.get_connected()

# Recon
data = c.db_read(1, 0, 30)
print(f"DB1 first 30 bytes: {data.hex()}")

# Attack
c.db_write(1, 0, b"\x27\x0f")    # write 9999 (big-endian uint16) to DBW0

c.disconnect()
```

**Q1.3.a — Auth provided:** none. The protocol does not require
any. `snap7.Client.connect()` opens a COTP session and an S7
Setup Communication exchange — neither carries credentials.

This is the lever Stuxnet pulled: legitimate Step7 software speaks
this same protocol to the same PLC with the same zero-auth
handshake. Stuxnet didn't break crypto; it became a legitimate
master.

---

## §2 — OPC UA

### §2.1 — Browse the address space

Expected output of `browse_opcua.py`:

```
Objects/
  ProcessVariables/
    P1_FT01_intake_flow_1     (Double)  ns=2
    P1_FT01Z_intake_flow_1z   (Double)  ns=2
    P1_FT02_transfer_flow     (Double)  ns=2
    ... (15 total)
```

**Q2.1.a — Attacker-economics shift:** Modbus and S7 require the
attacker to either know the register/DB map in advance (vendor
docs, leaked project files) or guess. OPC UA serves the map up to
any client that connects. Recon collapses from "find docs / leak
files" to "open a session, walk the tree." A targeted attack no
longer needs vendor documentation.

**Q2.1.b — Example NodeIds:**
- `ns=2;s=P1_PIT01_pressure_1`
- `ns=2;s=P1_TIT01_temperature_1`
- `ns=2;s=P1_LIT01_tank_level`

The string identifiers come from how the server constructed the
nodes; OPC UA also supports numeric NodeIds, GUIDs, opaque bytes.

### §2.2 — Subscribe

Expected solution (your_opcua_client.py):

```python
import asyncio
from asyncua import Client

class Handler:
    def datachange_notification(self, node, val, data):
        print(f"{node} = {val}")

async def main():
    async with Client("opc.tcp://plc-opcua:4840/lab/") as c:
        node = c.get_node("ns=2;s=P1_PIT01_pressure_1")
        sub = await c.create_subscription(100, Handler())
        await sub.subscribe_data_change(node)
        await asyncio.sleep(30)

asyncio.run(main())
```

**Q2.2.a — Why push vs poll matters:** in poll model, the proxy
hits every tag every cycle whether or not it changed — wasteful
when 90% of OT data is steady-state, and worse, you miss
sub-second transitions if your poll interval is 1 s. Push model
notifies only on change and can carry millisecond-level events
without burning bandwidth on idle tags. This is why Open Automation
and Industry 4.0 conversations favor OPC UA + MQTT over Modbus.

**Q2.2.b — Cascading diode redesign:**
1. `ot-proxy` would have to maintain a persistent OPC UA session
   with active subscriptions, not a per-cycle poll
2. Events would need to be buffered + timestamped, then framed
   into the diode's UDP wire format with their original event
   timestamps, not the proxy's send timestamp
3. The IT-side `it-proxy` would need a notion of "this tag changed,
   here's the value at time T" instead of "here's the latest
   snapshot from poll cycle N"
4. Grafana would need to handle sparse, irregular time series, not
   1-Hz regular ones
A real diode product handles all of this. The lab simplifies by
polling.

### §2.3 — Security flip

**Q2.3.a — Default mode attack:** succeeds. The server accepts
anonymous sessions over the `None` policy. `node.set_writable()`
was set on the server side, so any anonymous client can write.

**Q2.3.b — Secure mode attack failure:** the asyncua client raises
`UaError: No matching endpoints: 1, http://opcfoundation.org/UA/SecurityPolicy#None`
during *endpoint discovery* (before `OpenSecureChannel` is even
attempted). The client asks the server "what endpoints do you offer
that accept SecurityPolicy=None?" and the answer is "none of them" —
the server only advertises endpoints that require Basic256Sha256 +
Sign & Encrypt. The handshake terminates before any session is
created and before any data byte is exchanged.

The OPC UA spec's `BadSecurityChecksFailed` (0x80130000) is the
status code servers return when crypto verification fails *after*
channel open; here we're failing earlier, at policy negotiation.
Same lesson either way: the protocol refuses to talk.

The student's attack.py never gets to the read or write — it's
killed at the handshake. That's the *point* of protocol-layer
security: rejection happens before the attacker can do anything.

**Q2.3.c — Snort against each mode:**
- **Open mode:** yes, a rule like "alert on OPC UA write to NodeId
  X" is writeable. The cleartext payload contains the NodeId and
  the value — Snort 3's OPC UA preprocessor or even raw-byte
  matching can detect it.
- **Secure mode:** no signature rule is possible. The bytes on the
  wire are AES-encrypted post-`OpenSecureChannel`. You'd be
  detecting connections, not contents — and the connection itself
  is legitimate-looking.

This is the strongest argument for protocol-layer security: it
*replaces* the signature-IDS layer, it doesn't supplement it. A
Snort rule is your insurance when the protocol can't authenticate;
when the protocol can, you don't need the rule.

---

## §3 — Synthesis table (expected fill)

| | Modbus | S7comm | OPC UA |
|---|---|---|---|
| Default port | 502 | **102** | **4840** |
| Bytes to read 1 tag | 12 | **31** | varies (200+) |
| Setup handshake | none | **TPKT + COTP + S7 Setup Comm** | **HEL/ACK + OpenSecChan + CreateSession + Activate** |
| Can browse the address space? | ❌ | **❌ (need DB map)** | **✅** |
| Polling model | poll only | **poll only** | **poll + subscribe** |
| Default auth in this lab | none | **none** | **none (policy=None)** |
| Auth available if configured? | **❌** | **partial (S7-1500 ≥ FW 4.5)** | **✅ (Basic256Sha256 + cert)** |
| Famous breach | **Maroochy Shire (2000)** | **Stuxnet (2010)** | **none yet (it's young)** |

**Q3.a — Which protocols gave you the option:** Only OPC UA, fully.
S7-1500 firmware 4.5+ gives partial protocol-layer security but
it's off by default and rarely turned on. Modbus has no answer at
the protocol layer — you can wrap Modbus in TLS (Modbus Secure,
2018), but it requires both ends to support a separate non-default
mode and is essentially never deployed.

**Q3.b — Expected sentence (the takeaway):**

> "Protocol modernity bought one thing — *the option to
> authenticate. Whether anyone uses that option is an operator
> decision, not a protocol decision.*"

Strong students might also say:

> "Modbus had no choices to make about security because the era
> didn't allow them. OPC UA forces operators to make those
> choices on purpose. The danger is that 'None' is still an
> option, and 'None' looks like 'works' from a green-light SCADA
> perspective."

---

## Common student mistakes

- **Forgetting `socket.gethostbyname()` in the S7 client:** libsnap7
  is a C library and does not call the libc resolver. Connect
  fails with "Connection refused" or hangs.
- **Not setting `set_writable()` on OPC UA writes:** asyncua server
  has been configured to allow writes; student clients sometimes
  trip on "BadUserAccessDenied" if they were testing against a
  different OPC UA server in their notes.
- **Running `attack.py --protocol opcua` after `up.sh` without
  installing the server cert:** expected — that's the point of
  §2.3. If students think the failure is a bug, redirect: "the
  protocol is supposed to stop you here."
- **Confusing OPC UA NodeId namespaces:** `ns=0` is the standard
  base nodeset; the lab's variables live in `ns=2`. Students who
  try `ns=1;s=...` get NotFound.

---

## Expected lab state after `provision.sh`

| | Status |
|---|---|
| `plc-modbus`, `plc-s7`, `plc-opcua` | Running on `ot-net`, in default config |
| `attacker` container | Rebuilt with `snap7` + `asyncua` Python libs |
| `/lab/pcaps/multi.pcap` | 30 s, all three protocols present |
| `/lab/tools/` mounted into attacker | rw — students edit the `your_*_client.py` stubs |
| `lab_protocols/opcua-secure/certs/` | empty until `up.sh` runs |

After `bash lab_protocols/opcua-secure/up.sh`:
- `plc-opcua` restarted with `OPCUA_SECURITY=basic256sha256`
- `lab_protocols/opcua-secure/certs/server-cert.{pem,der}` generated
- The OPC UA endpoint now requires `Basic256Sha256 + Sign&Encrypt`
- `down.sh` reverts to default (no rebuild needed, just env flip)
