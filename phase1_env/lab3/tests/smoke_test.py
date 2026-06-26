"""
smoke_test.py — End-to-end smoke test against a running Lab 3 server.

Walks one group of 4 students all the way from LOBBY → DEBRIEF, casts a vote,
verifies pressure ticks arrive, and confirms the outcome message is delivered.

Usage:
    # In one terminal:
    LAB3_EVENTS_DIR=/tmp/lab3_events \
    LAB3_INSTRUCTOR_TOKEN=test123 \
    LAB3_PRESSURE_TICK_SECONDS=0.5 \
    .lab3_venv/bin/uvicorn phase1_env.lab3.server.app:app --host 127.0.0.1 --port 8080

    # In another terminal:
    .lab3_venv/bin/python phase1_env/lab3/tests/smoke_test.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager

import httpx
import websockets

BASE_URL = os.environ.get("LAB3_BASE_URL", "http://127.0.0.1:8080")
WS_URL = BASE_URL.replace("http", "ws")
TOKEN = os.environ.get("LAB3_INSTRUCTOR_TOKEN", "test123")

ROLES = ["PLANT_MANAGER", "OT_ENGINEER", "IT_CYBER_LEAD", "PR"]


def banner(s: str) -> None:
    print(f"\n{'='*70}\n  {s}\n{'='*70}", flush=True)


def ok(s: str) -> None:
    print(f"  ✓ {s}", flush=True)


def fail(s: str) -> None:
    print(f"  ✗ {s}", flush=True)
    sys.exit(1)


# ── Instructor REST helpers ───────────────────────────────────────────────

async def instructor_state(client: httpx.AsyncClient) -> dict:
    r = await client.get(f"{BASE_URL}/api/instructor/state", params={"token": TOKEN})
    r.raise_for_status()
    return r.json()


async def instructor_advance(client: httpx.AsyncClient) -> dict:
    r = await client.post(f"{BASE_URL}/api/instructor/advance", params={"token": TOKEN})
    r.raise_for_status()
    return r.json()


async def instructor_inject2(client: httpx.AsyncClient) -> dict:
    r = await client.post(f"{BASE_URL}/api/instructor/inject2", params={"token": TOKEN})
    r.raise_for_status()
    return r.json()


# ── Student WS helper ─────────────────────────────────────────────────────

class Student:
    def __init__(self, group_id: str, student_id: str, role: str) -> None:
        self.group_id = group_id
        self.student_id = student_id
        self.role = role
        self.display_name = f"{role.title()} {student_id}"
        self.ws = None
        self.inbox: list[dict] = []
        self._reader_task: asyncio.Task | None = None

    async def connect(self) -> None:
        self.ws = await websockets.connect(f"{WS_URL}/ws/group/{self.group_id}")
        await self.ws.send(json.dumps({
            "type": "join",
            "student_id": self.student_id,
            "display_name": self.display_name,
            "role": self.role,
        }))
        self._reader_task = asyncio.create_task(self._reader())

    async def _reader(self) -> None:
        try:
            async for raw in self.ws:
                self.inbox.append(json.loads(raw))
        except Exception:
            pass

    async def vote(self, choice: str) -> None:
        await self.ws.send(json.dumps({"type": "vote", "choice": choice}))

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
        if self.ws:
            await self.ws.close()

    def find(self, msg_type: str) -> list[dict]:
        return [m for m in self.inbox if m.get("type") == msg_type]

    def latest_state(self) -> dict | None:
        states = self.find("state_update")
        return states[-1] if states else None


# ── Phase advance with logging ────────────────────────────────────────────

async def advance_to(client: httpx.AsyncClient, target: str) -> None:
    state = await instructor_state(client)
    while state["phase"] != target:
        result = await instructor_advance(client)
        print(f"    advance: {state['phase']} -> {result['phase']}", flush=True)
        state = result
        await asyncio.sleep(0.1)  # let state_update messages flush


# ── The smoke test ────────────────────────────────────────────────────────

async def main() -> None:
    banner("Lab 3 server smoke test")
    async with httpx.AsyncClient(timeout=10.0) as client:

        # 1. Initial state should be LOBBY
        s = await instructor_state(client)
        assert s["phase"] == "LOBBY", f"expected LOBBY, got {s['phase']}"
        ok(f"initial phase is LOBBY (session_id={s['session_id']}, seed={s['session_seed']})")

        # 2. Five students join group g1
        students = [Student("g7", f"stu{i}", ROLES[i]) for i in range(len(ROLES))]
        for stu in students:
            await stu.connect()
        await asyncio.sleep(0.5)
        ok(f"{len(ROLES)} students connected and joined group g7")

        # Verify each got an initial state_update
        for stu in students:
            st = stu.latest_state()
            if st is None:
                fail(f"{stu.student_id} never received state_update")
        ok("all students received initial state_update")

        # 3. Walk to NORMAL_OPS
        await advance_to(client, "NORMAL_OPS")
        await asyncio.sleep(0.3)
        for stu in students:
            st = stu.latest_state()
            if st["phase"] != "NORMAL_OPS":
                fail(f"{stu.student_id} stuck at {st['phase']}")
        ok("all clients see NORMAL_OPS")

        # 4. Trigger ransomware
        await advance_to(client, "INJECT_1_RANSOMWARE")
        await asyncio.sleep(0.3)
        await advance_to(client, "DISCUSSION_1")
        await asyncio.sleep(0.3)
        ok("ransomware → DISCUSSION_1")

        # 5. Fire INJECT_2 — pressure clock starts
        result = await instructor_inject2(client)
        assert result["phase"] == "INJECT_2_WORKER_RADIO"
        ok("inject2 fired → INJECT_2_WORKER_RADIO")

        # Plant Manager should now see show_gauge=True; others should not.
        await asyncio.sleep(0.3)
        pm = next(s for s in students if s.role == "PLANT_MANAGER")
        ops = next(s for s in students if s.role == "OT_ENGINEER")
        if not pm.latest_state()["show_gauge"]:
            fail("Plant Manager should see gauge")
        if ops.latest_state()["show_gauge"]:
            fail("Ops Lead should NOT see gauge")
        ok("gauge visibility correct per role")

        # 6. Wait for pressure ticks
        await asyncio.sleep(2.0)
        ticks = [m for m in pm.inbox if m.get("type") == "pressure_tick"]
        if len(ticks) < 2:
            fail(f"expected pressure ticks, got {len(ticks)}")
        last_tick = ticks[-1]
        g1_pressure = last_tick["groups"]["g7"]["pressure_bar"]
        ok(f"received {len(ticks)} pressure ticks; latest g1={g1_pressure} bar")

        # 7. Advance to ULTIMATUM and vote
        await advance_to(client, "DISCUSSION_2")
        await asyncio.sleep(0.2)
        await advance_to(client, "ULTIMATUM")
        await asyncio.sleep(0.3)
        ok("at ULTIMATUM; opening voting")

        # 3 vote A (majority), 2 vote B
        # 4 students: 3 vote A (majority), 1 votes B.
        await students[0].vote("A")
        await students[1].vote("A")
        await students[2].vote("A")
        await students[3].vote("B")
        await asyncio.sleep(0.5)

        # Tally should be visible via vote_tally messages
        tallies = [m for m in students[0].inbox if m.get("type") == "vote_tally"]
        if not tallies:
            fail("no vote_tally messages received")
        final_tally = tallies[-1]["tally"]
        assert final_tally == {"A": 3, "B": 1}, f"got {final_tally}"
        ok(f"vote tally correct: {final_tally}")

        # 8. Advance to OUTCOME — should resolve to shutdown
        await advance_to(client, "OUTCOME")
        await asyncio.sleep(0.5)
        pm_state = pm.latest_state()
        if "outcome" not in pm_state:
            fail(f"no outcome in state_update: keys={list(pm_state.keys())}")
        outcome = pm_state["outcome"]
        if outcome["result_key"] != "shutdown":
            fail(f"expected shutdown, got {outcome['result_key']}")
        ok(f"outcome resolved: {outcome['result_key']} (${outcome['cost_usd']:,}, {outcome['casualties']} casualties)")

        # 9. DEBRIEF
        await advance_to(client, "DEBRIEF")
        ok("reached DEBRIEF")

        # 10. Verify event log file exists with sensible content
        events_dir = os.environ.get("LAB3_EVENTS_DIR", "/tmp/lab3_events")
        session_id = s["session_id"]
        log_path = os.path.join(events_dir, f"{session_id}.jsonl")
        if not os.path.exists(log_path):
            fail(f"event log not found at {log_path}")
        with open(log_path) as f:
            lines = f.readlines()
        types = [json.loads(line)["type"] for line in lines]
        for required in ("session_start", "group_join", "phase_advance", "vote_cast", "outcome_resolved"):
            if required not in types:
                fail(f"event log missing {required!r}")
        ok(f"event log: {len(lines)} lines, all required types present")

        # 11. Cleanup
        for stu in students:
            await stu.close()

    banner("ALL SMOKE TESTS PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
