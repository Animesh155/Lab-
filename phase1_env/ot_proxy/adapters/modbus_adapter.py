"""
modbus_adapter.py — Modbus TCP client for the OT proxy

This is the BRIDGE between Modbus protocol and our universal sensor struct.

What it does:
  1. Connects to a Modbus TCP server (the fake PLC)
  2. Reads all 15 holding registers in one batch (efficient)
  3. Applies scaling factors to convert raw int16 → meaningful float
  4. Returns readings in our universal format

What it outputs (per sensor):
  {
    'timestamp': int (UNIX epoch),
    'tag_id':    int (16-bit tag identifier),
    'value':     float (engineering units),
    'quality':   int (0x00=GOOD, 0xFF=COMM_FAIL),
  }

The rest of the OT proxy (frame builder, sender) doesn't care
that this data came from Modbus. The adapter pattern hides
protocol details from the diode pipeline.
"""

import time
import logging
from pymodbus.client import ModbusTcpClient


# ── Tag mapping ─────────────────────────────────────────────────────────
# Maps Modbus register address → universal tag_id + metadata
# This is what would normally come from a config file in production.

# Mapping when PLC uses HAI dataset replay
# (Real industrial values from Korea ETRI HAI 21.03 testbed)
# Scale here matches scale in hai_replay.py — must be consistent
MODBUS_TAG_MAP = {
    # reg : (tag_id, name,                       scale, quality_default)
    0:  (0x0101, 'P1_FT01_intake_flow_1',       10,   0x00),
    1:  (0x0102, 'P1_FT01Z_intake_flow_1z',     1,    0x00),
    2:  (0x0103, 'P1_FT02_transfer_flow',       1,    0x00),
    3:  (0x0104, 'P1_FT03_output_flow',         10,   0x00),
    4:  (0x0105, 'P1_LIT01_tank_level',         10,   0x00),
    5:  (0x0106, 'P1_LCV01D_lvl_valve_D',       100,  0x00),
    6:  (0x0107, 'P1_LCV01Z_lvl_valve_Z',       100,  0x00),
    7:  (0x0108, 'P1_PIT01_pressure_1',         1000, 0x00),
    8:  (0x0109, 'P1_PIT02_pressure_2',         1000, 0x00),
    9:  (0x010A, 'P1_PCV01D_press_valve_D',     100,  0x00),
    10: (0x010B, 'P1_PCV01Z_press_valve_Z',     100,  0x00),
    11: (0x010C, 'P1_TIT01_temperature_1',      100,  0x00),
    12: (0x010D, 'P1_TIT02_temperature_2',      100,  0x00),
    13: (0x010E, 'P1_FCV03D_flow_valve_D',      100,  0x00),
    14: (0x010F, 'P1_FCV03Z_flow_valve_Z',      100,  0x00),
}

QUALITY_GOOD       = 0x00
QUALITY_COMM_FAIL  = 0xFF


# ── Modbus Adapter ──────────────────────────────────────────────────────
class ModbusAdapter:
    """
    Polls a Modbus TCP PLC and returns normalized sensor readings.

    Usage:
      adapter = ModbusAdapter(host='plc-modbus', port=502)
      adapter.connect()
      readings = adapter.poll()  # returns list of dicts
    """

    def __init__(self, host, port=502, unit_id=1, tag_map=None):
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.tag_map = tag_map or MODBUS_TAG_MAP
        self.client = None
        self.log = logging.getLogger('modbus_adapter')

    def connect(self):
        """Open Modbus TCP connection. Returns True on success."""
        self.client = ModbusTcpClient(host=self.host, port=self.port)
        connected = self.client.connect()
        if connected:
            self.log.info(f"Connected to Modbus PLC at {self.host}:{self.port}")
        else:
            self.log.error(f"Failed to connect to {self.host}:{self.port}")
        return connected

    def poll(self):
        """
        Read all configured registers in one batch.
        Returns list of normalized reading dicts.
        On error: returns list with COMM_FAIL quality.
        """
        if not self.client or not self.client.connected:
            if not self.connect():
                return self._comm_fail_readings()

        timestamp = int(time.time())
        readings = []

        # Read all 15 registers in ONE Modbus request (much more efficient
        # than 15 separate reads — this is how real PLCs are polled)
        num_registers = max(self.tag_map.keys()) + 1
        try:
            result = self.client.read_holding_registers(
                address=0,
                count=num_registers,
                slave=self.unit_id,
            )
        except Exception as e:
            self.log.error(f"Modbus read exception: {e}")
            return self._comm_fail_readings()

        if result.isError():
            self.log.error(f"Modbus read error: {result}")
            return self._comm_fail_readings()

        # Parse each register through the tag map
        for reg_addr, (tag_id, name, scale, _) in self.tag_map.items():
            raw = result.registers[reg_addr]
            value = raw / scale   # apply scaling factor

            readings.append({
                'timestamp': timestamp,
                'tag_id':    tag_id,
                'value':     float(value),
                'quality':   QUALITY_GOOD,
                'name':      name,   # bonus: useful for logging
            })

        return readings

    def _comm_fail_readings(self):
        """When PLC is unreachable, emit COMM_FAIL frames for all tags.

        This is important: IT side should KNOW the OT side lost the PLC,
        not just receive silence.
        """
        timestamp = int(time.time())
        return [
            {
                'timestamp': timestamp,
                'tag_id':    tag_id,
                'value':     0.0,
                'quality':   QUALITY_COMM_FAIL,
                'name':      name,
            }
            for reg_addr, (tag_id, name, scale, _) in self.tag_map.items()
        ]

    def close(self):
        if self.client:
            self.client.close()
