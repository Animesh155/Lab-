#!/usr/bin/env python3
"""
subscribe_opcua.py — Subscribe to one OPC UA variable and print
every change.

Reference implementation the student adapts in §2.2. The key idea:
OPC UA can *push* changes; Modbus and S7 can only be *polled*. That
inverts the diode's polling assumption.

Usage:
    ./subscribe_opcua.py
    ./subscribe_opcua.py 'ns=2;s=P1_TIT01_temperature_1' 60
"""
import asyncio
import sys

from asyncua import Client


DEFAULT_URL = "opc.tcp://plc-opcua:4840/lab/"
DEFAULT_NODE = "ns=2;s=P1_PIT01_pressure_1"
DEFAULT_SECONDS = 30


class ChangeHandler:
    def datachange_notification(self, node, value, data):
        print(f"  {node.nodeid.to_string()}  =  {value}")


async def main(url: str, node_id: str, seconds: int):
    print(f"[sub] connecting to {url}")
    async with Client(url=url, timeout=4) as client:
        node = client.get_node(node_id)
        print(f"[sub] subscribing to {node_id} for {seconds} s")
        sub = await client.create_subscription(100, ChangeHandler())
        await sub.subscribe_data_change(node)
        await asyncio.sleep(seconds)
        await sub.delete()
        print("[sub] done")


if __name__ == "__main__":
    url = DEFAULT_URL
    node_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_NODE
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_SECONDS
    asyncio.run(main(url, node_id, seconds))
