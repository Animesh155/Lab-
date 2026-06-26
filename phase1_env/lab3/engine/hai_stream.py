"""
hai_stream.py — In-process HAI 21.03 sensor replay for Lab 3 NORMAL_OPS.

The Phase 1 Modbus PLC has its own HAI replay that scales values into int16
registers. For Lab 3 we want raw engineering values pushed straight to the
browser, so we read the same CSV but expose floats.

Reads `phase1_env/hai/hai-21.03/train1.csv.gz`, advances one row per call,
returns an 8-sensor dict keyed by the HMI tile element IDs (`s_reactor1_pressure`
etc.) — so app.js can map values → DOM with one trivial loop. Loops at EOF.
"""

from __future__ import annotations

import csv
import gzip
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("lab3.hai_stream")


# HMI tile ID  →  HAI column name. The keys must match the <div id="..."> in
# phase1_env/lab3/web/index.html. The HAI column names come from train1.csv.gz
# (real Korean ETRI water-plant testbed data).
SENSOR_MAP: dict[str, str] = {
    "s_reactor1_pressure": "P1_PIT01",   # ~1.31 bar — reactor pressure
    "s_reactor1_temp":     "P1_TIT01",   # ~35 °C — reactor temp
    "s_feed_flow":         "P1_FT01",    # ~165 L/min — intake/feed flow
    "s_tank_level":        "P1_LIT01",   # ~395 mm — tank level
    "s_outlet_flow":       "P1_FT03",    # ~246 L/min — outlet flow
    "s_pump_a":            "P1_LCV01D",  # ~10.8 % — level valve position
    "s_pump_b":            "P1_FCV01D",  # ~100 % — feed valve position
    "s_valve":             "P1_PCV01D",  # ~37 % — pressure ctrl valve
}


class HAIStream:
    """Stateful iterator over HAI rows. Not thread-safe — caller schedules ticks."""

    def __init__(self, csv_gz_path: Path) -> None:
        self.path = Path(csv_gz_path)
        self._file = None
        self._reader: Optional[csv.reader] = None
        self._col_idx: dict[str, int] = {}
        self._last: dict[str, float] = {label: 0.0 for label in SENSOR_MAP}
        self._row_count = 0
        self._open()

    def _open(self) -> None:
        if self._file is not None:
            self._file.close()
        log.info("opening HAI CSV: %s", self.path)
        self._file = gzip.open(self.path, "rt")
        self._reader = csv.reader(self._file)
        header = next(self._reader)
        self._col_idx = {}
        for label, hai_col in SENSOR_MAP.items():
            try:
                self._col_idx[label] = header.index(hai_col)
            except ValueError:
                log.warning("HAI column %s not in CSV — value will stay 0", hai_col)
                self._col_idx[label] = -1
        self._row_count = 0

    def next_row(self) -> dict[str, float]:
        """Advance one row; return the current 8-sensor snapshot."""
        try:
            row = next(self._reader)  # type: ignore[arg-type]
            self._row_count += 1
        except StopIteration:
            log.info("HAI EOF after %d rows; looping", self._row_count)
            self._open()
            row = next(self._reader)  # type: ignore[arg-type]
            self._row_count = 1

        for label, idx in self._col_idx.items():
            if idx < 0:
                continue
            try:
                self._last[label] = float(row[idx])
            except (ValueError, IndexError):
                pass
        return dict(self._last)

    def latest(self) -> dict[str, float]:
        """Last-known snapshot without advancing — used to freeze on INJECT_1."""
        return dict(self._last)

    def rewind(self) -> None:
        """Reopen the CSV from the top — used on session reset."""
        self._open()
        self._last = {label: 0.0 for label in SENSOR_MAP}
