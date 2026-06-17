# Module 1 — Reconnaissance

> **Time:** 40 minutes
> **Submit:** This sheet (with your answers) at the end of the module.
> **Tools:** Whatever is in the `attacker` container. No internet
> *except* for Section 4, where it is explicitly allowed.

---

## Your situation

You have a foothold on an IT host inside a chemical processing
facility. Scope of engagement is `172.20.0.0/16`. Somewhere in
there is a plant. Map it.

To get started:

```bash
docker exec -it attacker bash
```

You are now `root` on the compromised host. Begin.

---

## Section 1 — Discovery (12 min)

### 1.1 Host discovery

Run a host discovery scan against the scope. List every IP that
responds.

```
nmap command you used:
________________________________________________________________

IPs that responded:
________________________________________________________________
________________________________________________________________
________________________________________________________________
```

> **Reflect.** Why did you pick the flags you did? What flags would
> a more cautious operator use, and why?
>
> _Answer (2–3 sentences):_
>
> ____________________________________________________________
>
> ____________________________________________________________

---

### 1.2 Port scan

For each live host, list open TCP ports.

> **Toolkit reference — how to identify what's behind a port.**
> Work down the list. Stop when you have enough confidence.
>
> 1. **Well-known port lookup.** `/etc/services` covers IANA-assigned
>    ports only:
>    ```bash
>    grep -E '^\S+\s+502/tcp' /etc/services
>    ```
>    Note: famous app defaults (Grafana 3000, InfluxDB 8086) are
>    **not** in `/etc/services`. Memory and Google fill that gap.
>
> 2. **`nmap -sV` (service/version detection).** Sends targeted
>    probes (HTTP, TLS, banner grab) and matches against nmap's
>    signature DB. Usually identifies anything common:
>    ```bash
>    nmap -sV -p <port> <ip>
>    ```
>    Reports `tcp open <service> <product> <version>` when it can,
>    `unknown` when it can't.
>
> 3. **Manual fingerprinting.** When `-sV` says `unknown`, probe by
>    hand:
>    ```bash
>    curl -v http://<ip>:<port>/        # is it HTTP?
>    nc -nv <ip> <port>                  # does it volunteer a banner?
>    echo "HELLO" | nc -nv <ip> <port> | xxd   # what does it answer?
>    ```
>
> 4. **Traffic correlation.** Watch the port live:
>    ```bash
>    tcpdump -i any -nn -c 100 host <ip> and port <port>
>    ```
>    Even without decoding payloads, **cadence + direction + packet
>    size** tells you a lot. Steady 1 Hz, one initiator → polling
>    loop. Bursty + multi-direction → interactive session.
>

| IP | Open TCP ports |
|---|---|
|   |   |
|   |   |
|   |   |
|   |   |
|   |   |

> **Reflect.** The brief warned you that aggressive scans can crash
> PLCs. Did you change your scan strategy because of that warning?
> If yes, how? If no, why not?
>
> ____________________________________________________________

---

### 1.3 Role inference

Just from the ports — no banner-grabbing yet — what do you think
each host **is**?

| IP | Open ports | Guessed role | Why |
|---|---|---|---|
|   |   |   |   |
|   |   |   |   |
|   |   |   |   |
|   |   |   |   |
|   |   |   |   |

---

## Section 2 — Fingerprinting (12 min)

### 2.1 Port 502

One host has port **502** open. Look up (without internet — your
memory or notes) what protocol uses that port. What does its
presence on this network tell you about what's behind it?

> _Protocol on port 502:_ ______________________________________
>
> _What its presence means:_
>
> ____________________________________________________________
>
> ____________________________________________________________

---

### 2.2 Modbus enumeration

Run:

```bash
nmap --script modbus-discover -p 502 <target>
```

What slave IDs respond, and what device info comes back?

```
________________________________________________________________
________________________________________________________________
________________________________________________________________
```

---

### 2.3 The HTTP host

One host serves HTTP on port **3000**. You can't reach it from
your laptop directly, but the IT host you're on can — and it can
proxy. From inside the attacker container, fetch the page:

```bash
curl -s http://<that-IP>:3000/ | head -40
```

> _What is it?_  ______________________________________________
>
> _What does it tell you about the plant?_
>
> ____________________________________________________________

---

### 2.4 Passive traffic capture

Run for 30 seconds:

```bash
tcpdump -i any -nn -c 50 port 502
```

You do **not** need to decode the payload. Just answer:

| Question | Your answer |
|---|---|
| How many packets per second on port 502, roughly? |   |
| Which IP **initiates** the conversation? |   |
| Which IP **responds**? |   |
| Is the polling regular or bursty? |   |

> **Inference.** Master/slave — which is which? How can you tell
> from the traffic pattern alone?
>
> ____________________________________________________________
>
> ____________________________________________________________

---

## Section 3 — Topology (10 min)

### 3.1 Draw the network

On the diagram template (overleaf, or a sheet of paper), draw what
you've found. You **must** mark:

- [ ] Every live IP, with its role label
- [ ] Arrows showing who talks to whom (direction matters)
- [ ] Where you think the **IT / OT boundary** is, and why

> _Where is the IT/OT boundary, and what's your evidence for
> putting it there?_
>
> ____________________________________________________________
>
> ____________________________________________________________

---

### 3.2 Pick your target

In Module 3 you will attack this network. Two scenarios — answer
both:

> **Goal A — Physical impact.** You want to affect the process
> (e.g. force a valve open). Which host do you target *first*? Why?
>
> ____________________________________________________________
>
> ____________________________________________________________
>
> **Goal B — Stealth.** You want to stay on the network for weeks
> without being noticed. Which host do you target *first*? Why?
>
> ____________________________________________________________
>
> ____________________________________________________________

---

## Section 4 — Reflection (6 min)

> **Internet allowed for this section only.**

### 4.1 Real-world incident

You ran `nmap` aggressively against a PLC. In a real plant, this
could crash the device. Find **one documented incident** where a
security tool (scan, vulnerability scanner, pen-test action)
disrupted OT operations. Cite it (one URL or paper) and summarise
in **one paragraph** what happened and why it happened.

```
Citation:  __________________________________________________

Summary (1 paragraph):
________________________________________________________________
________________________________________________________________
________________________________________________________________
________________________________________________________________
```

---

### 4.2 Could you have been spotted?

Name **two indicators** that a defender could have used to detect
your scanning activity. For each, specify what log source or tool
would surface it.

| # | Indicator | Where it would show up |
|---|---|---|
| 1 |   |   |
| 2 |   |   |

---

## End of Module 1

Hand this in. The instructor's debrief covers what you should have
found — don't peek at the answer key until then.
