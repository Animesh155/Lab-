"""
hai_replay.py — Real HAI dataset replay for Modbus PLC simulator

Instead of generating synthetic sensor values, this module:
  1. Reads rows from the HAI 21.03 dataset (real industrial sensor data)
  2. On each tick, advances to the next row
  3. Returns 15 selected sensor values that match our Modbus PLC slots

The HAI dataset (Korea ETRI):
  - 4 PLC stages (P1, P2, P3, P4) — power + water hybrid testbed
  - 83 sensor signals at 1 Hz sampling
  - 60 hours of data per file
  - 38 labeled attack scenarios (in test/ files)

We use train1.csv.gz (60 hrs of NORMAL data) for now.
Later we'll switch to test files with attack labels for ML testing.

SENSOR MAPPING — our Modbus slot → HAI column:
  Our slot 0  intake_pump_1_speed       → P1_PP01AR  (pump A run signal/RPM)
  Our slot 1  intake_pump_1_current     → P1_PP01AD  (pump A diagnostic)
  Our slot 2  intake_pump_2_speed       → P1_PP01BR  (pump B run signal)
  Our slot 3  intake_pump_2_current     → P1_PP01BD  (pump B diagnostic)
  Our slot 4  raw_water_flow            → P1_FT01    (flow transmitter 1)
  Our slot 5  raw_water_turbidity       → P1_TIT01   (temp indicator — proxy for quality)
  Our slot 6  intake_pressure           → P1_PIT01   (pressure indicator 1)
  Our slot 7  tank_level                → P1_LIT01   (level indicator 1)
  Our slot 8  tank_temperature          → P1_TIT02   (temp indicator 2)
  Our slot 9  tank_ph                   → P1_PIT02   (we don't have pH, use PIT02)
  Our slot 10 transfer_valve_position   → P1_FCV01Z  (flow control valve 1 position)
  Our slot 11 transfer_flow             → P1_FT02    (flow transmitter 2)
  Our slot 12 plc_status                → P1_STSP    (PLC status setpoint)
  Our slot 13 alarm_count               → P1_B2004   (binary signal, proxy for alarm)
  Our slot 14 cycle_time                → P1_B3005   (binary signal, proxy for cycle)
"""

import csv
import gzip
import os
import logging

log = logging.getLogger('hai_replay')


# ── Sensor slot → HAI column name + scale factor ────────────────────────
#
# Scale factor: register_value = int(engineering_value * scale)
#               engineering_value = register_value / scale
#
# Chosen based on actual HAI 21.03 value ranges:
#   P1_FT01    ~165   → scale 10  → reg ~1650  (fits)
#   P1_FT02    ~1975  → scale 1   → reg ~1975  (fits)
#   P1_FT03    ~246   → scale 10  → reg ~2460  (fits)
#   P1_LIT01   ~395   → scale 10  → reg ~3950  (fits)
#   P1_TIT01   ~35    → scale 100 → reg ~3540  (good precision)
#   P1_PIT01   ~1.31  → scale 1000→ reg ~1310  (good precision)
#   P1_FCV03D  ~52    → scale 100 → reg ~5200
#   P1_LCV01D  ~10.8  → scale 1000→ reg ~10860 (good precision)
#   P1_PCV01D  ~37    → scale 100 → reg ~3700
#
HAI_MAPPING = [
    ('P1_FT01',     10),   # 0: intake flow 1 (real: ~165 L/min)
    ('P1_FT01Z',     1),   # 1: intake flow 1 secondary (real: ~825)
    ('P1_FT02',      1),   # 2: transfer flow (real: ~1975 L/min)
    ('P1_FT03',     10),   # 3: output flow (real: ~246)
    ('P1_LIT01',    10),   # 4: tank level (real: ~395)
    ('P1_LCV01D',  100),   # 5: level control valve D (real: ~10.8 %)
    ('P1_LCV01Z',  100),   # 6: level control valve Z (real: ~10.3 %)
    ('P1_PIT01',  1000),   # 7: pressure 1 (real: ~1.31 bar)
    ('P1_PIT02',  1000),   # 8: pressure 2 (real: ~0.28 bar)
    ('P1_PCV01D',  100),   # 9: pressure control valve (real: ~37 %)
    ('P1_PCV01Z',  100),   # 10: pressure ctrl valve Z (real: ~37 %)
    ('P1_TIT01',   100),   # 11: temperature 1 (real: ~35 °C)
    ('P1_TIT02',   100),   # 12: temperature 2 (real: ~35.7 °C)
    ('P1_FCV03D',  100),   # 13: flow control valve D (real: ~52 %)
    ('P1_FCV03Z',  100),   # 14: flow control valve Z (real: ~52.8 %)
]


class HAIReplaySensorArray:
    """
    Replaces the synthetic sensors with real HAI dataset replay.

    On each update():
      - Move to next row in CSV
      - For each of 15 sensor slots, read the mapped HAI column

    On get_raw_array():
      - Return the 15 raw int16 values to write to Modbus registers

    Loops back to the beginning when the file ends.
    """

    def __init__(self, csv_gz_path):
        self.csv_gz_path = csv_gz_path
        self.column_indices = []   # which CSV columns map to our slots
        self.scales = [m[1] for m in HAI_MAPPING]
        self.column_names = [m[0] for m in HAI_MAPPING]
        self.current_values = [0.0] * 15
        self.row_count = 0
        self.total_rows_read = 0

        self._file = None
        self._reader = None
        self._open_file()

    def _open_file(self):
        """Open (or reopen) the CSV and map column names to indices."""
        if self._file:
            self._file.close()

        log.info(f"Opening HAI dataset: {self.csv_gz_path}")
        self._file = gzip.open(self.csv_gz_path, 'rt')
        self._reader = csv.reader(self._file)

        # Read header and find our 15 columns
        header = next(self._reader)
        log.info(f"HAI file has {len(header)} columns, {self.row_count or '?'} rows total")

        self.column_indices = []
        for hai_col in self.column_names:
            try:
                idx = header.index(hai_col)
                self.column_indices.append(idx)
            except ValueError:
                log.warning(f"Column {hai_col} not in HAI file — using 0")
                self.column_indices.append(-1)

        self.total_rows_read = 0

    def update(self, dt=1.0):
        """Advance to next row in the CSV. Loop at end."""
        try:
            row = next(self._reader)
            self.total_rows_read += 1
        except StopIteration:
            # End of file — loop back
            log.info(f"HAI replay completed {self.total_rows_read} rows, looping")
            self._open_file()
            row = next(self._reader)
            self.total_rows_read = 1

        # Extract our 15 sensor values
        for i, col_idx in enumerate(self.column_indices):
            if col_idx == -1:
                self.current_values[i] = 0.0
            else:
                try:
                    self.current_values[i] = float(row[col_idx])
                except (ValueError, IndexError):
                    self.current_values[i] = 0.0

    def get_raw_array(self):
        """Return list of 15 int16 values for Modbus registers."""
        raw = []
        for value, scale in zip(self.current_values, self.scales):
            scaled = int(abs(value) * scale)  # abs in case of negative noise
            raw.append(max(0, min(65535, scaled)))
        return raw

    def get_engineering_values(self):
        """Return current values for logging (engineering units)."""
        return list(zip(self.column_names, self.current_values))


# ── Compatibility wrapper to match the old sensor array interface ──────
# (modbus_server.py expects a list of sensor objects with .update() and .get_raw())
class HAISensorAdapter:
    """Wraps HAIReplaySensorArray so modbus_server.py can use it as a list."""

    def __init__(self, replay_array, index):
        self.replay = replay_array
        self.index = index
        self.name = HAI_MAPPING[index][0]
        self.scale = HAI_MAPPING[index][1]

    @property
    def value(self):
        return self.replay.current_values[self.index]

    def update(self, dt=1.0):
        # Only the FIRST sensor advances the replay; rest are read-only
        if self.index == 0:
            self.replay.update(dt)

    def get_raw(self):
        return self.replay.get_raw_array()[self.index]


def build_hai_sensor_array(csv_gz_path='/app/data/train1.csv.gz'):
    """
    Build the 15 sensor objects, all sharing one HAIReplaySensorArray.
    """
    if not os.path.exists(csv_gz_path):
        log.error(f"HAI data file not found: {csv_gz_path}")
        raise FileNotFoundError(csv_gz_path)

    replay = HAIReplaySensorArray(csv_gz_path)
    return [HAISensorAdapter(replay, i) for i in range(15)]
