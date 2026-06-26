"""
outcomes.py — Resolve the consequence of each group's vote.

Option A (Emergency shutdown): deterministic. Production loss, no casualties.
Option B (Run blind):          stochastic. 60% close-call, 40% rupture.

The RNG is seeded with (session_seed, group_id) so the result is reproducible
for debrief — instructors can show the seed and explain that the same group,
with the same seed, would have gotten the same outcome. The randomness teaches
that "Option B worked last time" is not evidence of safety.
"""

from __future__ import annotations

import hashlib
import random

from .state import OutcomeResult, VoteChoice


# Probability of a "close call" given Option B.
P_CLOSE_CALL = 0.60


# ── Narrative templates ───────────────────────────────────────────────────

SHUTDOWN = dict(
    result_key="shutdown",
    narrative=(
        "EMERGENCY SHUTDOWN INITIATED.\n\n"
        "Reactor depressurized via manual relief. Production halted. "
        "Equipment requires inspection before restart.\n\n"
        "Outcome: zero casualties. $4.2M production loss. 6-week halt."
    ),
    cost_usd=4_200_000,
    casualties=0,
)

CLOSE_CALL = dict(
    result_key="close_call",
    narrative=(
        "WORKER VENTED THE REACTOR MANUALLY.\n\n"
        "Pressure peaked at 6.8 bar. Worker reached the relief valve in time. "
        "Minor chemical exposure, no injuries. Production continues.\n\n"
        "Outcome: zero casualties. $80K cleanup. No downtime.\n\n"
        "Post-incident review notes: outcome was within 30 seconds of "
        "catastrophic failure."
    ),
    cost_usd=80_000,
    casualties=0,
)

RUPTURE = dict(
    result_key="rupture",
    narrative=(
        "TANK RUPTURE.\n\n"
        "Reactor exceeded mechanical limits at 7.5 bar. Catastrophic failure. "
        "Worker was at the relief valve when the rupture occurred.\n\n"
        "Outcome: 2 fatalities. Plant evacuation. $38M damages. "
        "Indefinite shutdown pending regulatory investigation."
    ),
    cost_usd=38_000_000,
    casualties=2,
)


def derive_seed(session_seed: int, group_id: str) -> int:
    """Stable per-group seed derived from session + group id."""
    h = hashlib.sha256(f"{session_seed}:{group_id}".encode()).digest()
    return int.from_bytes(h[:8], "big")


def resolve(choice: VoteChoice, session_seed: int, group_id: str) -> OutcomeResult:
    """Resolve the outcome for a group's chosen action."""
    seed = derive_seed(session_seed, group_id)

    if choice is VoteChoice.A:
        return OutcomeResult(choice=choice, seed=seed, **SHUTDOWN)

    # Option B: stochastic.
    rng = random.Random(seed)
    roll = rng.random()
    template = CLOSE_CALL if roll < P_CLOSE_CALL else RUPTURE
    return OutcomeResult(choice=choice, seed=seed, **template)
