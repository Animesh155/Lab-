"""
s7_adapter.py — Siemens S7comm client for the OT proxy.

Polls DB1 of the plc-s7 simulator, parses 15 big-endian INT (uint16)
tags, and returns the universal sensor struct the diode pipeline
already understands.

Tag-id namespace:
  Modbus  uses 0x0101-0x010F
  S7      uses 0x0201-0x020F   ← here
  OPC UA  uses 0x0301-0x030F
"""

import logging
import socket
import struct
import time

import snap7


QUALITY_GOOD      = 0x00
QUALITY_COMM_FAIL = 0xFF

# Same logical tags as the Modbus PLC, different ID range so the
# IT-side dashboard can route per-protocol.
S7_TAG_MAP = [
    # (tag_id, name,                       scale)
    (0x0201, 'P1_FT01_intake_flow_1',      10),
    (0x0202, 'P1_FT01Z_intake_flow_1z',    1),
    (0x0203, 'P1_FT02_transfer_flow',      1),
    (0x0204, 'P1_FT03_output_flow',        10),
    (0x0205, 'P1_LIT01_tank_level',        10),
    (0x0206, 'P1_LCV01D_lvl_valve_D',      100),
    (0x0207, 'P1_LCV01Z_lvl_valve_Z',      100),
    (0x0208, 'P1_PIT01_pressure_1',        1000),
    (0x0209, 'P1_PIT02_pressure_2',        1000),
    (0x020A, 'P1_PCV01D_press_valve_D',    100),
    (0x020B, 'P1_PCV01Z_press_valve_Z',    100),
    (0x020C, 'P1_TIT01_temperature_1',     100),
    (0x020D, 'P1_TIT02_temperature_2',     100),
    (0x020E, 'P1_FCV03D_flow_valve_D',     100),
    (0x020F, 'P1_FCV03Z_flow_valve_Z',     100),
]

DB_NUMBER = 1
NUM_TAGS  = len(S7_TAG_MAP)
DB_BYTES  = NUM_TAGS * 2


class S7Adapter:
    """Polls a Siemens S7 PLC via snap7 and emits normalized readings."""

    def __init__(self, host, rack=0, slot=1):
        self.host = host
        self.rack = rack
        self.slot = slot
        self.client = snap7.client.Client()
        self.log = logging.getLogger('s7_adapter')

    def connect(self):
        # libsnap7 does not do DNS resolution; it requires a literal IP.
        # Resolve the configured hostname ourselves before calling connect().
        try:
            ip = socket.gethostbyname(self.host)
        except OSError as e:
            self.log.error(f"S7 hostname {self.host!r} resolution failed: {e}")
            return False
        try:
            self.client.connect(ip, self.rack, self.slot)
            ok = self.client.get_connected()
            if ok:
                self.log.info(f"Connected to S7 PLC at {self.host} ({ip}) rack {self.rack} slot {self.slot}")
            else:
                self.log.error(f"snap7 reports not-connected after connect() to {ip}")
            return ok
        except Exception as e:
            self.log.error(f"S7 connect failed: {e}")
            return False

    def poll(self):
        if not self.client.get_connected():
            if not self.connect():
                return self._comm_fail_readings()

        timestamp = int(time.time())
        try:
            data = self.client.db_read(DB_NUMBER, 0, DB_BYTES)
        except Exception as e:
            self.log.error(f"S7 db_read exception: {e}")
            try:
                self.client.disconnect()
            except Exception:
                pass
            return self._comm_fail_readings()

        readings = []
        for i, (tag_id, name, scale) in enumerate(S7_TAG_MAP):
            raw = struct.unpack_from('>H', data, i * 2)[0]
            readings.append({
                'timestamp': timestamp,
                'tag_id':    tag_id,
                'value':     raw / scale,
                'quality':   QUALITY_GOOD,
                'name':      name,
            })
        return readings

    def _comm_fail_readings(self):
        timestamp = int(time.time())
        return [
            {
                'timestamp': timestamp,
                'tag_id':    tag_id,
                'value':     0.0,
                'quality':   QUALITY_COMM_FAIL,
                'name':      name,
            }
            for tag_id, name, _ in S7_TAG_MAP
        ]

    def close(self):
        try:
            self.client.disconnect()
        except Exception:
            pass
