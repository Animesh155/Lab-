"""
s7_server.py — Fake Siemens S7-1200 PLC speaking S7comm over TCP/102.

Uses python-snap7's Server class, which wraps the libsnap7 C library
and handles the full S7comm + COTP + TPKT stack so the wire-level
fingerprint (TPKT magic 0x03, COTP CR/CC, S7comm setup) looks like a
real Siemens PLC. That's the whole point for the recon lab — students
should see a different banner, different port, different payload
shape than the Modbus PLC.

What it exposes:
  - DB1 with 15 INT (16-bit big-endian) tags
  - Same logical process variables as the Modbus PLC (see process_sim.py)
  - Rack 0, Slot 1 (S7-1200 default)
  - TCP/102 (S7comm default)
"""

import ctypes
import logging
import threading
import time

import snap7
from snap7.server import Server
from snap7.type import SrvArea

from process_sim import ProcessSim, TAGS


logging.basicConfig(format="[S7-PLC] %(message)s", level=logging.INFO)
log = logging.getLogger()


DB_NUMBER = 1
NUM_TAGS = len(TAGS)
DB_BYTES = NUM_TAGS * 2   # one INT (16-bit) per tag

# Shared buffer the server exposes. snap7 hands clients a pointer to
# this memory; we mutate it from the update thread and the server
# reads it on demand.
db_buffer = (ctypes.c_uint8 * DB_BYTES)()


def update_loop():
    sim = ProcessSim()
    tick = 0
    while True:
        readings = sim.tick()
        for i, (name, value, raw) in enumerate(readings):
            # Big-endian uint16 — S7 INT is always BE on the wire.
            db_buffer[i * 2]     = (raw >> 8) & 0xff
            db_buffer[i * 2 + 1] = raw & 0xff
        tick += 1
        if tick % 10 == 0:
            summary = ", ".join(f"{n}={v:.1f}" for n, v, _ in readings[:3])
            log.info("tick %d — %s ...", tick, summary)
        time.sleep(1.0)


def main():
    log.info("=" * 60)
    log.info("  WATER TREATMENT PLANT — Siemens S7-1200 simulator")
    log.info("=" * 60)
    log.info("DB%d, %d INT tags, %d bytes", DB_NUMBER, NUM_TAGS, DB_BYTES)
    for i, (name, _, _, _) in enumerate(TAGS):
        log.info("  DB%d.DBW%d = %s", DB_NUMBER, i * 2, name)

    server = Server()
    server.register_area(SrvArea.DB, DB_NUMBER, db_buffer)

    threading.Thread(target=update_loop, daemon=True).start()

    log.info("Starting S7 server on 0.0.0.0:102 (rack 0, slot 1)")
    log.info("=" * 60)
    # start_to binds to a specific address; tcpport defaults to 102.
    server.start_to("0.0.0.0")

    # snap7's server runs in a C-side thread. Keep main alive.
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
