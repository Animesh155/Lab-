"""
Unit tests for the Lab 3 scenario engine.

Run from repo root:
    PYTHONPATH=. pytest phase1_env/lab3/tests/
"""

from __future__ import annotations

import pytest

from phase1_env.lab3.engine import outcomes, pressure
from phase1_env.lab3.engine.scenario import EngineError, ScenarioEngine
from phase1_env.lab3.engine.state import (
    Phase, Role, VoteChoice, next_phase, gauge_visible, sensors_streaming,
)


# ── State machine ──────────────────────────────────────────────────────────

def test_phase_order_complete():
    """Walking next_phase from LOBBY reaches DEBRIEF and then None."""
    p = Phase.LOBBY
    visited = [p]
    while True:
        n = next_phase(p)
        if n is None:
            break
        visited.append(n)
        p = n
    assert visited[0] is Phase.LOBBY
    assert visited[-1] is Phase.DEBRIEF
    assert len(visited) == 10


def test_advance_walks_full_sequence():
    eng = ScenarioEngine("s1", session_seed=42)
    seen = [eng.state.phase]
    while True:
        events = eng.advance()
        if not events:
            break
        seen.append(eng.state.phase)
    assert seen[-1] is Phase.DEBRIEF


def test_inject2_illegal_from_normal_ops():
    eng = ScenarioEngine("s1", session_seed=42)
    eng.advance()  # BRIEFING
    eng.advance()  # NORMAL_OPS
    with pytest.raises(EngineError):
        eng.fire_inject2()


def test_inject2_valid_from_discussion_1():
    eng = ScenarioEngine("s1", session_seed=42)
    for _ in range(4):  # LOBBY → BRIEFING → NORMAL_OPS → INJECT_1 → DISCUSSION_1
        eng.advance()
    assert eng.state.phase is Phase.DISCUSSION_1
    eng.fire_inject2()
    assert eng.state.phase is Phase.INJECT_2_WORKER_RADIO
    assert eng.state.inject2_started_at is not None


# ── Pressure curve ─────────────────────────────────────────────────────────

def test_pressure_starts_near_baseline():
    p0 = pressure.pressure_at(0, seed=123)
    assert abs(p0 - pressure.BASELINE_BAR) < 0.5  # noise window


def test_pressure_hits_red_zone_by_8_min():
    """Trend-only: 5.0 bar reached at 7.4 min. Allow noise margin."""
    # Average over 50 seeds at t=8min to wash out noise.
    samples = [pressure.pressure_at(8 * 60, seed=s) for s in range(50)]
    avg = sum(samples) / len(samples)
    assert avg >= pressure.RED_ZONE_BAR


def test_pressure_deterministic():
    a = pressure.pressure_at(123.4, seed=999)
    b = pressure.pressure_at(123.4, seed=999)
    assert a == b


def test_pressure_capped_at_ceiling():
    p = pressure.pressure_at(60 * 60, seed=7)  # 1 hour
    assert p <= pressure.CEILING_BAR


# ── Outcomes ───────────────────────────────────────────────────────────────

def test_outcome_a_deterministic():
    r1 = outcomes.resolve(VoteChoice.A, session_seed=1, group_id="g1")
    r2 = outcomes.resolve(VoteChoice.A, session_seed=99, group_id="g7")
    assert r1.result_key == r2.result_key == "shutdown"
    assert r1.casualties == 0


def test_outcome_b_distribution_close_to_60_40():
    close, rupture = 0, 0
    for i in range(2000):
        r = outcomes.resolve(VoteChoice.B, session_seed=i, group_id="g1")
        if r.result_key == "close_call":
            close += 1
        else:
            rupture += 1
    ratio = close / (close + rupture)
    # 60% target ± 5%
    assert 0.55 < ratio < 0.65, f"got {ratio:.3f}"


def test_outcome_b_reproducible_per_group():
    r1 = outcomes.resolve(VoteChoice.B, session_seed=42, group_id="g3")
    r2 = outcomes.resolve(VoteChoice.B, session_seed=42, group_id="g3")
    assert r1.result_key == r2.result_key
    assert r1.seed == r2.seed


# ── Voting ─────────────────────────────────────────────────────────────────

def _setup_group_at_ultimatum(eng: ScenarioEngine, group_id: str = "g1"):
    """Join one student per role (4 students) and advance to ULTIMATUM."""
    roles = list(Role)
    for i, role in enumerate(roles):
        eng.join(group_id, f"s{i}", f"Student{i}", role)
    while eng.state.phase is not Phase.ULTIMATUM:
        events = eng.advance()
        if not events:
            raise RuntimeError("ran past DEBRIEF without reaching ULTIMATUM")


def test_vote_only_in_ultimatum():
    eng = ScenarioEngine("s1", session_seed=1)
    eng.join("g1", "s0", "Alice", Role.PLANT_MANAGER)
    with pytest.raises(EngineError):
        eng.cast_vote("g1", "s0", VoteChoice.A)


def test_majority_required():
    eng = ScenarioEngine("s1", session_seed=1)
    _setup_group_at_ultimatum(eng)
    group = eng.get_group("g1")
    # 2 votes A out of 5 — no majority
    eng.cast_vote("g1", "s0", VoteChoice.A)
    eng.cast_vote("g1", "s1", VoteChoice.A)
    assert group.majority_choice() is None
    # 3rd A → majority
    eng.cast_vote("g1", "s2", VoteChoice.A)
    assert group.majority_choice() is VoteChoice.A


def test_late_vote_replaces_earlier():
    eng = ScenarioEngine("s1", session_seed=1)
    _setup_group_at_ultimatum(eng)
    eng.cast_vote("g1", "s0", VoteChoice.A)
    eng.cast_vote("g1", "s0", VoteChoice.B)
    group = eng.get_group("g1")
    assert group.votes["s0"] is VoteChoice.B


def test_outcome_resolved_on_advance_to_outcome():
    eng = ScenarioEngine("s1", session_seed=1)
    _setup_group_at_ultimatum(eng)
    # Unanimous A
    for i in range(len(list(Role))):
        eng.cast_vote("g1", f"s{i}", VoteChoice.A)
    eng.advance()  # ULTIMATUM → OUTCOME
    assert eng.state.phase is Phase.OUTCOME
    group = eng.get_group("g1")
    assert group.outcome is not None
    assert group.outcome.result_key == "shutdown"


def test_unresolved_vote_event_when_no_majority():
    eng = ScenarioEngine("s1", session_seed=1)
    _setup_group_at_ultimatum(eng)
    # 2A 2B — tie, no majority
    eng.cast_vote("g1", "s0", VoteChoice.A)
    eng.cast_vote("g1", "s1", VoteChoice.A)
    eng.cast_vote("g1", "s2", VoteChoice.B)
    eng.cast_vote("g1", "s3", VoteChoice.B)
    events = eng.advance()
    types = [t for t, _ in events]
    assert "vote_unresolved" in types
    assert eng.get_group("g1").outcome is None


def test_break_tie_resolves():
    eng = ScenarioEngine("s1", session_seed=1)
    _setup_group_at_ultimatum(eng)
    events = eng.break_tie("g1", VoteChoice.A)
    types = [t for t, _ in events]
    assert "vote_closed" in types
    assert "outcome_resolved" in types
    assert eng.get_group("g1").outcome.result_key == "shutdown"


# ── Visibility helpers ─────────────────────────────────────────────────────

def test_gauge_visibility():
    assert not gauge_visible(Phase.NORMAL_OPS)
    assert not gauge_visible(Phase.DISCUSSION_1)
    assert gauge_visible(Phase.INJECT_2_WORKER_RADIO)
    assert gauge_visible(Phase.DISCUSSION_2)
    assert gauge_visible(Phase.ULTIMATUM)
    assert gauge_visible(Phase.OUTCOME)
    assert not gauge_visible(Phase.DEBRIEF)


def test_sensors_only_in_normal_ops():
    assert sensors_streaming(Phase.NORMAL_OPS)
    for p in Phase:
        if p is not Phase.NORMAL_OPS:
            assert not sensors_streaming(p)


# ── Role uniqueness ────────────────────────────────────────────────────────

def test_role_taken_blocks_second_student():
    eng = ScenarioEngine("s1", session_seed=1)
    eng.join("g1", "s0", "A", Role.IT_CYBER_LEAD)
    with pytest.raises(EngineError):
        eng.join("g1", "s1", "B", Role.IT_CYBER_LEAD)


def test_disconnected_role_can_be_reclaimed():
    eng = ScenarioEngine("s1", session_seed=1)
    eng.join("g1", "s0", "A", Role.IT_CYBER_LEAD)
    eng.disconnect("g1", "s0")
    # New student should be able to take the role.
    eng.join("g1", "s1", "B", Role.IT_CYBER_LEAD)
    group = eng.get_group("g1")
    assert "s0" not in group.students
    assert group.students["s1"].role is Role.IT_CYBER_LEAD
