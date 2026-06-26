"""
opcua_server.py — OPC UA PLC simulator (TCP/4840).

OPC UA is the modern ICS protocol the Modbus/S7 generation is being
replaced by: typed address space, sessions, optional TLS. Lab runs an
unencrypted endpoint so students see the OPC UA Binary protocol on the
wire (Hello/Ack handshake, OpenSecureChannel even on policy None).

Exposes opc.tcp://plc-opcua:4840/lab/ with Objects.ProcessVariables.<Tag>
— 15 Double variables, one per plant tag, updated every second.
"""

import asyncio
import logging

from asyncua import Server, ua

from process_sim import ProcessSim, TAGS


logging.basicConfig(format="[OPCUA-PLC] %(message)s", level=logging.INFO)
log = logging.getLogger()


ENDPOINT = "opc.tcp://0.0.0.0:4840/lab/"
NAMESPACE_URI = "http://lab.diode/plc"
UPDATE_INTERVAL = 1.0


async def main():
    log.info("=" * 60)
    log.info("  WATER TREATMENT PLANT — OPC UA simulator")
    log.info("=" * 60)

    server = Server()
    await server.init()
    server.set_endpoint(ENDPOINT)
    server.set_server_name("Lab Process PLC (OPC UA)")
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])

    idx = await server.register_namespace(NAMESPACE_URI)
    log.info("Namespace %s registered as ns=%d", NAMESPACE_URI, idx)

    container = await server.nodes.objects.add_object(idx, "ProcessVariables")

    variables = []
    for name, _, _, _ in TAGS:
        node = await container.add_variable(idx, name, 0.0, ua.VariantType.Double)
        await node.set_writable()
        variables.append((name, node))

    sim = ProcessSim()

    async with server:
        log.info("OPC UA server up at %s — %d variables", ENDPOINT, len(variables))
        log.info("=" * 60)
        tick = 0
        while True:
            readings = sim.tick()
            for (name, node), (_, value, _) in zip(variables, readings):
                await node.write_value(value)
            tick += 1
            if tick % 10 == 0:
                summary = ", ".join(f"{n}={v:.1f}" for n, v, _ in readings[:3])
                log.info("tick %d — %s ...", tick, summary)
            await asyncio.sleep(UPDATE_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
