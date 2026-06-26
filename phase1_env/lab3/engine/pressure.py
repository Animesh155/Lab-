"""
pressure.py — Stochastic linear pressure curve for INJECT_2.

The chemical reactor pressure climbs after the worker radio inject. Curve:

    pressure(t) = baseline + slope * minutes + noise(t)

  baseline = 1.3 bar (normal operating pressure)
  slope    = 0.5 bar/minute
  noise    = small Gaussian, σ ≈ 0.08, smoothed so the gauge needle wiggles
             realistically instead of jumping every sample.

Hard ceiling at 7.5 bar (mechanical relief valve in the fiction).
Red zone starts at 5.0 bar (~7.4 min after inject).

The function is deterministic given (elapsed_seconds, seed). Same seed and time
always returns the same value — so the debrief can replay a group's exact curve.
"""

from __future__ import annotations

import math
import random


BASELINE_BAR = 1.3
SLOPE_BAR_PER_MIN = 0.5
NOISE_SIGMA = 0.08
CEILING_BAR = 7.5
RED_ZONE_BAR = 5.0


def pressure_at(elapsed_seconds: float, seed: int) -> float:
    """
    Return the pressure (bar) at `elapsed_seconds` after INJECT_2 fired.

    Deterministic in (elapsed_seconds, seed). We bucket time into 1-second
    cells so consecutive calls within the same second return the same value
    — this keeps WebSocket pushes stable and avoids jitter.
    """
    if elapsed_seconds < 0:
        return BASELINE_BAR

    minutes = elapsed_seconds / 60.0
    trend = BASELINE_BAR + SLOPE_BAR_PER_MIN * minutes

    # Smoothed noise: blend two seeded RNG samples (current second + prior)
    # so the value moves gradually instead of teleporting.
    second = int(elapsed_seconds)
    n_now = _seeded_gauss(seed, second)
    n_prev = _seeded_gauss(seed, max(0, second - 1))
    frac = elapsed_seconds - second
    noise = (1 - frac) * n_prev + frac * n_now

    return min(CEILING_BAR, max(0.0, trend + noise))


def _seeded_gauss(seed: int, tick: int) -> float:
    """Deterministic Gaussian sample for (seed, tick)."""
    rng = random.Random((seed * 1_000_003) ^ tick)
    return rng.gauss(0.0, NOISE_SIGMA)


def in_red_zone(pressure_bar: float) -> bool:
    return pressure_bar >= RED_ZONE_BAR


def seconds_to_red_zone(seed: int) -> float:
    """Approximate seconds until red zone (ignoring noise). For instructor UI."""
    # 5.0 = 1.3 + 0.5 * minutes  ->  minutes = 7.4
    return (RED_ZONE_BAR - BASELINE_BAR) / SLOPE_BAR_PER_MIN * 60.0
