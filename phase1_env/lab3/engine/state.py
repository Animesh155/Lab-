"""
state.py — Lab 3 scenario state models.

Defines the phase state machine, role assignments, and per-group/global state
containers. Pure data + transition rules — no I/O, no side effects.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from datetime import datetime, timezone

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────

class Phase(str, Enum):
    """Global scenario phase. Advances in order, instructor-driven."""
    LOBBY = "LOBBY"
    BRIEFING = "BRIEFING"
    NORMAL_OPS = "NORMAL_OPS"
    INJECT_1_RANSOMWARE = "INJECT_1_RANSOMWARE"
    DISCUSSION_1 = "DISCUSSION_1"
    INJECT_2_WORKER_RADIO = "INJECT_2_WORKER_RADIO"
    DISCUSSION_2 = "DISCUSSION_2"
    ULTIMATUM = "ULTIMATUM"
    OUTCOME = "OUTCOME"
    DEBRIEF = "DEBRIEF"


# Canonical linear order. Used by advance() and to enforce legal transitions.
PHASE_ORDER: list[Phase] = [
    Phase.LOBBY,
    Phase.BRIEFING,
    Phase.NORMAL_OPS,
    Phase.INJECT_1_RANSOMWARE,
    Phase.DISCUSSION_1,
    Phase.INJECT_2_WORKER_RADIO,
    Phase.DISCUSSION_2,
    Phase.ULTIMATUM,
    Phase.OUTCOME,
    Phase.DEBRIEF,
]


class Role(str, Enum):
    """Four canonical roles per group (spec: Plant Manager, OT Engineer,
    IT/Cyber Lead, PR). Groups of 4 use all four; groups of 5 leave the
    instructor's chosen 5th role unfilled or doubled up."""
    PLANT_MANAGER = "PLANT_MANAGER"
    OT_ENGINEER = "OT_ENGINEER"
    IT_CYBER_LEAD = "IT_CYBER_LEAD"
    PR = "PR"


class VoteChoice(str, Enum):
    """Ultimatum vote — A = emergency shutdown, B = run blind."""
    A = "A"  # Emergency shutdown
    B = "B"  # Ignore warning, keep running


# ── Models ─────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Student(BaseModel):
    """One connected student."""
    student_id: str               # sticky cookie ID
    display_name: str
    role: Role
    connected: bool = True
    joined_at: str = Field(default_factory=_now_iso)


class OutcomeResult(BaseModel):
    """Resolved outcome for a group after the vote closes."""
    choice: VoteChoice
    result_key: str               # "shutdown" | "close_call" | "rupture"
    narrative: str
    cost_usd: int                 # 0 for safe outcomes, dollar damages otherwise
    casualties: int               # human cost
    seed: int                     # for replay / debrief reproducibility


class GroupState(BaseModel):
    """Per-group state. Phase comes from GlobalState; this tracks group-local."""
    group_id: str
    students: dict[str, Student] = Field(default_factory=dict)   # student_id -> Student
    votes: dict[str, VoteChoice] = Field(default_factory=dict)   # student_id -> choice
    vote_closed: bool = False
    outcome: Optional[OutcomeResult] = None
    # Last-known PLC snapshot frozen at INJECT_1 — what the locked HMI shows.
    frozen_sensors: Optional[dict[str, float]] = None

    def connected_students(self) -> list[Student]:
        return [s for s in self.students.values() if s.connected]

    def vote_tally(self) -> dict[str, int]:
        tally = {VoteChoice.A.value: 0, VoteChoice.B.value: 0}
        for choice in self.votes.values():
            tally[choice.value] += 1
        return tally

    def majority_choice(self) -> Optional[VoteChoice]:
        """Return winning choice if a strict majority of *connected* members voted, else None."""
        connected = self.connected_students()
        n = len(connected)
        if n == 0:
            return None
        needed = n // 2 + 1
        tally = self.vote_tally()
        if tally[VoteChoice.A.value] >= needed:
            return VoteChoice.A
        if tally[VoteChoice.B.value] >= needed:
            return VoteChoice.B
        return None


class GlobalState(BaseModel):
    """Top-level session state. One instance per running session."""
    session_id: str
    phase: Phase = Phase.LOBBY
    phase_started_at: str = Field(default_factory=_now_iso)
    groups: dict[str, GroupState] = Field(default_factory=dict)
    # Set when INJECT_2_WORKER_RADIO fires — used by pressure curve.
    inject2_started_at: Optional[str] = None
    # Random base seed for this session. Combined with group_id for outcomes.
    session_seed: int = 0


# ── Transition rules ───────────────────────────────────────────────────────

def next_phase(current: Phase) -> Optional[Phase]:
    """Return the next phase in canonical order, or None at DEBRIEF."""
    idx = PHASE_ORDER.index(current)
    if idx + 1 >= len(PHASE_ORDER):
        return None
    return PHASE_ORDER[idx + 1]


def can_advance(current: Phase) -> bool:
    return next_phase(current) is not None


def is_locked_phase(p: Phase) -> bool:
    """True for phases where the HMI is ransomware-locked."""
    return p in {
        Phase.INJECT_1_RANSOMWARE,
        Phase.DISCUSSION_1,
        Phase.INJECT_2_WORKER_RADIO,
        Phase.DISCUSSION_2,
        Phase.ULTIMATUM,
    }


def gauge_visible(p: Phase) -> bool:
    """True when the pressure gauge should be visible to the Plant Manager role."""
    return p in {
        Phase.INJECT_2_WORKER_RADIO,
        Phase.DISCUSSION_2,
        Phase.ULTIMATUM,
        Phase.OUTCOME,
    }


def sensors_streaming(p: Phase) -> bool:
    """True when live HAI sensor values should flow to clients."""
    return p == Phase.NORMAL_OPS
