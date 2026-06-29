#!/usr/bin/env python3
"""
browse_opcua.py — Walk the OPC UA address space of plc-opcua.

This is the demo that lands §2.1: OPC UA hands out the tag map
without authentication. Modbus and S7 require you to know it in
advance. Run this against any new OPC UA server and you get the
attacker's reconnaissance for free.

Usage:
    ./browse_opcua.py
    ./browse_opcua.py opc.tcp://other-host:4840/lab/
"""
import asyncio
import sys

from asyncua import Client


DEFAULT_URL = "opc.tcp://plc-opcua:4840/lab/"


async def walk(node, depth=0, max_depth=4):
    cls = await node.read_node_class()
    name = (await node.read_browse_name()).Name
    type_str = ""
    if cls == 2:  # Variable
        try:
            value = await node.read_value()
            type_str = f"  = {value!r}"
        except Exception:
            type_str = "  (unreadable)"

    nodeid_str = node.nodeid.to_string()
    print(f"{'  ' * depth}- {name}  [{nodeid_str}]{type_str}")

    if depth >= max_depth:
        return
    for child in await node.get_children():
        # Skip standard nodeset noise above ns=2.
        if depth == 0 and child.nodeid.NamespaceIndex == 0:
            continue
        await walk(child, depth + 1, max_depth)


async def main(url: str):
    print(f"[browse] connecting to {url}")
    async with Client(url=url, timeout=4) as client:
        print("[browse] address space:")
        await walk(client.nodes.objects)


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    asyncio.run(main(url))
