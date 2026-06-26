"""
process_sim.py — Tiny plant simulator shared by the non-Modbus PLCs.

Produces the same 15 logical tags as the Modbus PLC, so students can
compare protocols without comparing data. Values drift around a
setpoint with Gaussian noise — enough motion to make polling visible
on a dashboard, not enough to look random.

Each tick returns a list of (name, value_float, raw_uint16) triples.
"""

import random


# (tag_name, setpoint, noise_sigma, scale)
# scale converts the engineering-units float into a uint16 the way the
# Modbus PLC does it, so an S7 INT or OPC UA UInt16 carries the same
# numeric content as the matching Modbus register.
TAGS = [
    ("P1_FT01_intake_flow_1",     250.0,  4.0,   10),
    ("P1_FT01Z_intake_flow_1z",   2500.0, 40.0,  1),
    ("P1_FT02_transfer_flow",     1800.0, 30.0,  1),
    ("P1_FT03_output_flow",       220.0,  3.0,   10),
    ("P1_LIT01_tank_level",       650.0,  8.0,   10),
    ("P1_LCV01D_lvl_valve_D",     50.0,   2.0,   100),
    ("P1_LCV01Z_lvl_valve_Z",     50.0,   2.0,   100),
    ("P1_PIT01_pressure_1",       3.2,    0.05,  1000),
    ("P1_PIT02_pressure_2",       2.8,    0.05,  1000),
    ("P1_PCV01D_press_valve_D",   45.0,   1.5,   100),
    ("P1_PCV01Z_press_valve_Z",   45.0,   1.5,   100),
    ("P1_TIT01_temperature_1",    21.5,   0.3,   100),
    ("P1_TIT02_temperature_2",    22.0,   0.3,   100),
    ("P1_FCV03D_flow_valve_D",    60.0,   2.0,   100),
    ("P1_FCV03Z_flow_valve_Z",    60.0,   2.0,   100),
]


class ProcessSim:
    def __init__(self):
        self.state = [t[1] for t in TAGS]

    def tick(self):
        """Advance one second. Returns list of (name, float, uint16)."""
        out = []
        for i, (name, sp, noise, scale) in enumerate(TAGS):
            # Mean-revert toward setpoint + Gaussian noise.
            self.state[i] += (sp - self.state[i]) * 0.1
            self.state[i] += random.gauss(0, noise)
            raw = max(0, min(65535, int(self.state[i] * scale)))
            out.append((name, float(self.state[i]), raw))
        return out
