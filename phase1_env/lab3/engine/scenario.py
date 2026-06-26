"""
scenario.py — Core scenario engine.

Pure logic, no I/O. Owns global phase, per-group state, vote handling, and
transition rules. The FastAPI layer (server/app.py) wires WebSockets and event
logging on top.

Threading model: single asyncio event loop. The engine is *not* thread-safe;
callers must mutate it from the event loop only. Each public method is
synchronous and returns a list of "events" the caller should broadcast/log.
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from typing import Optional

from .state import (
    Phase,
    Role,
    VoteChoice,
    Student,
    GlobalState,
    GroupState,
    OutcomeResult,
    next_phase,
    is_locked_phase,
)
from . import outcomes


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EngineError(Exception):
    """Raised when a caller requests an illegal operation."""


class ScenarioEngine:
    """
    Owns one full Lab 3 session: global phase + N groups + votes + outcomes.

    All public methods return a list of (event_type, payload) tuples that the
    server layer can fan out to WebSocket clients and append to the event log.
    """

    def __init__(self, session_id: str, session_seed: Optional[int] = None) -> None:
        if session_seed is None:
            session_seed = random.SystemRandom().randrange(2**31)
        self.state = GlobalState(session_id=session_id, session_seed=session_seed)
        self._inject2_monotonic_start: Optional[float] = None

    # ── Read helpers ───────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Full state as a dict — used for instructor dashboard polls."""
        return self.state.model_dump(mode="json")

    def get_group(self, group_id: str) -> GroupState:
        if group_id not in self.state.groups:
            raise EngineError(f"unknown group {group_id!r}")
        return self.state.groups[group_id]

    def inject2_elapsed_seconds(self) -> float:
        """Seconds since INJECT_2 fired, or 0 if it hasn't."""
        if self._inject2_monotonic_start is None:
            return 0.0
        return max(0.0, time.monotonic() - self._inject2_monotonic_start)

    # ── Student lifecycle ──────────────────────────────────────────────────

    def ensure_group(self, group_id: str) -> GroupState:
        """Get-or-create a group container."""
        if group_id not in self.state.groups:
            self.state.groups[group_id] = GroupState(group_id=group_id)
        return self.state.groups[group_id]

    def join(self, group_id: str, student_id: str, display_name: str, role: Role) -> list[tuple]:
        """Student joins (or reconnects to) a group with a role."""
        group = self.ensure_group(group_id)

        # Role must be unique within group, unless this student already held it.
        for sid, s in group.students.items():
            if s.role is role and sid != student_id:
                # Allow reclaim only if the previous holder is disconnected.
                if s.connected:
                    raise EngineError(f"role {role.value} already taken in group {group_id}")
                del group.students[sid]
                break

        existing = group.students.get(student_id)
        if existing is not None:
            existing.connected = True
            existing.role = role
            existing.display_name = display_name
            event_type = "reconnect"
        else:
            group.students[student_id] = Student(
                student_id=student_id,
                display_name=display_name,
                role=role,
            )
            event_type = "group_join"

        return [(event_type, {
            "group_id": group_id,
            "student_id": student_id,
            "role": role.value,
            "display_name": display_name,
        })]

    def disconnect(self, group_id: str, student_id: str) -> list[tuple]:
        group = self.ensure_group(group_id)
        s = group.students.get(student_id)
        if s is None:
            return []
        s.connected = False
        return [("disconnect", {"group_id": group_id, "student_id": student_id})]

    # ── Phase transitions ──────────────────────────────────────────────────

    def advance(self) -> list[tuple]:
        """Advance the global phase one step. Idempotent at DEBRIEF."""
        nxt = next_phase(self.state.phase)
        if nxt is None:
            return []  # already at DEBRIEF — silent no-op
        return self._transition_to(nxt)

    def fire_inject2(self) -> list[tuple]:
        """Special transition: DISCUSSION_1 → INJECT_2_WORKER_RADIO."""
        if self.state.phase is not Phase.DISCUSSION_1:
            raise EngineError(
                f"inject2 only valid from DISCUSSION_1, current is {self.state.phase.value}"
            )
        return self._transition_to(Phase.INJECT_2_WORKER_RADIO)

    def _transition_to(self, new_phase: Phase) -> list[tuple]:
        events: list[tuple] = []
        old = self.state.phase

        # Freeze sensors entering INJECT_1 — locked HMI shows last-known values.
        if new_phase is Phase.INJECT_1_RANSOMWARE and old is Phase.NORMAL_OPS:
            for g in self.state.groups.values():
                # frozen_sensors filled by server layer (it owns the HAI stream);
                # engine just ensures the slot exists so the lock screen renders.
                if g.frozen_sensors is None:
                    g.frozen_sensors = {}

        # Start the pressure clock entering INJECT_2.
        if new_phase is Phase.INJECT_2_WORKER_RADIO:
            self._inject2_monotonic_start = time.monotonic()
            self.state.inject2_started_at = _now_iso()

        # Resolve outcomes entering OUTCOME phase.
        if new_phase is Phase.OUTCOME:
            for group in self.state.groups.values():
                if group.outcome is None:
                    choice = group.majority_choice()
                    if choice is None:
                        # No majority by the time instructor advanced — log it
                        # and skip resolution; instructor may break tie manually.
                        events.append(("vote_unresolved", {"group_id": group.group_id}))
                        continue
                    group.vote_closed = True
                    group.outcome = outcomes.resolve(
                        choice, self.state.session_seed, group.group_id
                    )
                    events.append(("outcome_resolved", {
                        "group_id": group.group_id,
                        "outcome": group.outcome.model_dump(mode="json"),
                    }))

        self.state.phase = new_phase
        self.state.phase_started_at = _now_iso()
        events.insert(0, ("phase_advance", {
            "from": old.value, "to": new_phase.value,
            "at": self.state.phase_started_at,
        }))
        return events

    # ── Votes ──────────────────────────────────────────────────────────────

    def cast_vote(self, group_id: str, student_id: str, choice: VoteChoice) -> list[tuple]:
        if self.state.phase is not Phase.ULTIMATUM:
            raise EngineError(f"votes only accepted in ULTIMATUM, current is {self.state.phase.value}")
        group = self.get_group(group_id)
        if group.vote_closed:
            raise EngineError(f"voting closed for group {group_id}")
        if student_id not in group.students:
            raise EngineError(f"student {student_id} not in group {group_id}")
        # Late vote replaces earlier vote — final answer wins.
        group.votes[student_id] = choice
        return [("vote_cast", {
            "group_id": group_id,
            "student_id": student_id,
            "choice": choice.value,
            "tally": group.vote_tally(),
        })]

    def break_tie(self, group_id: str, choice: VoteChoice) -> list[tuple]:
        """Instructor casting vote — forces resolution and closes voting."""
        if self.state.phase is not Phase.ULTIMATUM:
            raise EngineError("tie-break only valid in ULTIMATUM")
        group = self.get_group(group_id)
        group.vote_closed = True
        group.outcome = outcomes.resolve(choice, self.state.session_seed, group_id)
        return [("vote_closed", {
            "group_id": group_id, "by": "instructor", "choice": choice.value,
        }), ("outcome_resolved", {
            "group_id": group_id,
            "outcome": group.outcome.model_dump(mode="json"),
        })]

    # ── Reset ──────────────────────────────────────────────────────────────

    def reset_group(self, group_id: str) -> list[tuple]:
        group = self.get_group(group_id)
        group.votes.clear()
        group.vote_closed = False
        group.outcome = None
        return [("group_reset", {"group_id": group_id})]

    def reset_session(self, new_session_id: str, new_seed: Optional[int] = None) -> list[tuple]:
        """Hard-reset the whole scenario.

        Returns a list of events. The caller is responsible for archiving the
        old event log file, swapping the EventLogger target, rewinding any
        external state (HAI cursor), and broadcasting fresh state to clients.
        """
        old_session_id = self.state.session_id
        old_seed = self.state.session_seed
        if new_seed is None:
            new_seed = random.SystemRandom().randrange(2**31)
        # Build a brand-new GlobalState — drops all groups/votes/outcomes/pressure.
        self.state = GlobalState(session_id=new_session_id, session_seed=new_seed)
        return [
            ("session_reset", {
                "old_session_id": old_session_id,
                "old_seed": old_seed,
                "new_session_id": self.state.session_id,
                "new_seed": self.state.session_seed,
            }),
            # phase_advance into LOBBY makes the broadcast layer push state to every
            # connected client without us needing a separate event type.
            ("phase_advance", {
                "from": "RESET",
                "to": Phase.LOBBY.value,
                "at": self.state.phase_started_at,
            }),
        ]
