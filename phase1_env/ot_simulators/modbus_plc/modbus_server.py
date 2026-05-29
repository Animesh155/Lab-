"""
modbus_server.py — Fake Modbus TCP PLC for Water Treatment Plant

What this does:
  1. Spins up a Modbus TCP server on port 502
  2. Exposes 15 holding registers (40001-40015) with realistic sensor data
  3. Updates sensor values every 1 second in a background thread
  4. Responds to Modbus read requests from any client (our OT proxy)

What a real PLC does:
  - Reads physical I/O (sensors wired to it)
  - Runs ladder logic (control rules)
  - Exposes data via Modbus/OPC UA/whatever
  - This simulator only fakes the last step

In production: this would be replaced by REAL hardware.
For testing: this gives us deterministic, debuggable sensor data
             that speaks the same protocol as a real PLC.
"""

import time
import threading
import logging

from pymodbus.server import StartTcpServer
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusSlaveContext,
    ModbusServerContext,
)

import os

# Choose data source: synthetic sensors or HAI dataset replay
USE_HAI_REPLAY = os.environ.get('USE_HAI_REPLAY', 'true').lower() == 'true'

if USE_HAI_REPLAY:
    from hai_replay import build_hai_sensor_array as build_sensor_array
else:
    from sensors import build_sensor_array


# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    format='[MODBUS-PLC] %(message)s',
    level=logging.INFO,
)
log = logging.getLogger()


# ── Sensor → Register Update Loop ────────────────────────────────────────
def sensor_update_loop(sensors, datablock, interval=1.0):
    """
    Background thread: update sensor values and write to Modbus registers.

    Real PLCs scan physical I/O every few milliseconds.
    We simulate at 1 Hz which is plenty for testing.
    """
    log.info(f"Sensor update loop started ({len(sensors)} sensors, {interval}s interval)")

    tick_count = 0
    while True:
        try:
            # Update every sensor (physics simulation)
            for sensor in sensors:
                sensor.update(dt=interval)

            # Push current values to Modbus registers
            # Write at offset 1 (pymodbus quirk — see main() comment)
            raw_values = [s.get_raw() for s in sensors]
            datablock.setValues(1, raw_values)

            tick_count += 1

            # Print summary every 10 ticks (10 seconds)
            if tick_count % 10 == 0:
                summary = ", ".join(
                    f"{s.name}={s.value:.1f}" for s in sensors[:5]
                )
                log.info(f"tick {tick_count} — {summary} ...")

            time.sleep(interval)
        except Exception as e:
            log.error(f"Update loop error: {e}")
            time.sleep(interval)


# ── Main ─────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("  WATER TREATMENT PLANT — Modbus TCP PLC Simulator")
    log.info("=" * 60)

    # Build the sensor array
    sensors = build_sensor_array()
    log.info(f"Initialized {len(sensors)} sensors:")
    for i, s in enumerate(sensors):
        log.info(f"  reg[{i:2d}] = {s.name:30s} scale={s.scale}")

    # Create Modbus datastore — holding registers (40001-40015)
    # Use create() to pre-allocate full 65536 register range with zeros.
    #
    # PYMODBUS QUIRK: The slave context shifts addresses by 1 internally.
    # Protocol address 0 → datablock index 1.
    # So to make protocol read at address 0 return our sensor values,
    # we must write them at datablock offset 1.
    holding_block = ModbusSequentialDataBlock.create()
    initial_values = [s.get_raw() for s in sensors]
    holding_block.setValues(1, initial_values)  # OFFSET 1, NOT 0

    slave_context = ModbusSlaveContext(
        hr=holding_block,  # holding registers
    )
    context = ModbusServerContext(slaves=slave_context, single=True)

    # Start sensor update thread BEFORE starting server
    update_thread = threading.Thread(
        target=sensor_update_loop,
        args=(sensors, holding_block),
        daemon=True,
    )
    update_thread.start()

    log.info("Starting Modbus TCP server on 0.0.0.0:502")
    log.info("Clients can read holding registers 0-14 with FC03")
    log.info("=" * 60)

    # Blocking — runs forever
    StartTcpServer(context=context, address=("0.0.0.0", 502))


if __name__ == "__main__":
    main()
