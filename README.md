# OT Security Training Lab — User Guide

## 1. Description

This lab simulates an industrial chemical plant. A hardware data diode separates the Information Technology (IT) network from the Operational Technology (OT) network. 

Students complete five modules:
- **Module 1:** Reconnaissance and network discovery.
- **Module 2:** Modbus protocol frame analysis.
- **Module 3:** Engineering workstation compromise and rogue PLC control.
- **Module 4:** Network traffic analysis with Zeek and Snort.
- **Module 5:** Siemens S7comm and OPC UA protocol control.

---

## 2. Prerequisites

Make sure that your computer has:
- Docker Engine version 24.0 or higher.
- Docker Compose version 2.20 or higher.
- A modern web browser.

---

## 3. Network Architecture

| Network Name | Subnet | Security Zone | Purpose |
|---|---|---|---|
| `it-net` | `172.20.30.0/24` | Corporate IT | Attacker foothold, SCADA HMI, Scoring Server. |
| `diode-net` | `172.20.20.0/24` | Diode Channel | Unidirectional hardware data diode link. |
| `ot-net` | `172.20.10.0/24` | Plant OT | Programmable Logic Controllers (PLCs). |

---

## 4. Start the Lab

1. Open your terminal.
2. Go to the lab folder:
   ```bash
   cd lab-ot-security
   ```
3. Start all containers:
   ```bash
   docker compose up --build -d
   ```
4. Verify that all containers run:
   ```bash
   docker compose ps
   ```

---

## 5. Web Interfaces

Open your web browser and navigate to these addresses:

- **Scoring Server:** `http://localhost:5000`  
  Submit flags and view the score board.
- **SCADA Dashboard (Grafana):** `http://localhost:3000`  
  View plant process data and alarm status.

---

## 6. Access Workstations

### 6.1 Attacker Workstation (Modules 1, 2, 3, and 5)
To start a shell in the `attacker` container, type:
```bash
docker exec -it attacker bash
```

This container includes:
- Task documents in `/modules/`.
- Network tools: `nmap`, `tshark`, `tcpdump`, `curl`.
- Python tools: `pymodbus`, `python-snap7`, `asyncua`.
- Attack scripts in `/lab/tools/`.
- Packet captures in `/lab/pcaps/`.

### 6.2 Defender Workstation (Module 4)
To start a shell in the `defender-tools` container, type:
```bash
docker exec -it defender-tools bash
```

This container includes:
- Zeek 8 with the `icsnpp-modbus` parser.
- Snort 2.9 with configuration files in `/lab/snort/`.
- Attack capture file at `/lab/pcaps/attack.pcap`.

---

## 7. Submit Flags

You can submit flags in two ways:

1. **Web Browser:**  
   Go to `http://localhost:5000` and submit the flag value.

2. **Terminal (from the `attacker` container):**  
   ```bash
   python3 /lab/tools/submit_flag.py <module-number> "<flag-string>"
   ```
   *Example:*
   ```bash
   python3 /lab/tools/submit_flag.py module1 "diode-live"
   ```

---

## 8. Stop the Lab

To stop and remove all containers and networks, type:
```bash
docker compose down -v
```
