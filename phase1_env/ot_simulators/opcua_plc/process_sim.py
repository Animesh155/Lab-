"""
process_sim.py — Same plant simulator the S7 PLC uses.

Duplicated rather than shared so each PLC's container is self-contained
(no cross-directory imports at build time).
"""

import random


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
        out = []
        for i, (name, sp, noise, scale) in enumerate(TAGS):
            self.state[i] += (sp - self.state[i]) * 0.1
            self.state[i] += random.gauss(0, noise)
            raw = max(0, min(65535, int(self.state[i] * scale)))
            out.append((name, float(self.state[i]), raw))
        return out
