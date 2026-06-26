"""
app.py — FastAPI server for Lab 3.

Wires the ScenarioEngine to:
  - Instructor REST endpoints (advance, inject2, reset, tie-break, state)
  - Student WebSocket /ws/group/{group_id}
  - Instructor WebSocket /ws/instructor
  - Periodic pressure-tick broadcaster during INJECT_2..ULTIMATUM

Auth: instructor endpoints require ?token=... matching env LAB3_INSTRUCTOR_TOKEN.
This is intentionally minimal — classroom use only.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import (
    Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect, status,
)
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field

from ..engine.scenario import ScenarioEngine, EngineError
from ..engine.state import Phase, Role, VoteChoice, gauge_visible, sensors_streaming
from ..engine import pressure as pressure_mod
from ..engine.hai_stream import HAIStream
from .broadcast import ConnectionRegistry
from .events import EventLogger

log = logging.getLogger("lab3.app")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


# ── Config ────────────────────────────────────────────────────────────────

EVENTS_DIR = Path(os.environ.get("LAB3_EVENTS_DIR", "/data/events"))
INSTRUCTOR_TOKEN = os.environ.get("LAB3_INSTRUCTOR_TOKEN", "instructor")
SESSION_ID = os.environ.get("LAB3_SESSION_ID") or f"session-{int(time.time())}"
PRESSURE_TICK_SECONDS = float(os.environ.get("LAB3_PRESSURE_TICK_SECONDS", "1.0"))
SENSOR_TICK_SECONDS = float(os.environ.get("LAB3_SENSOR_TICK_SECONDS", "1.0"))
HAI_CSV_PATH = Path(os.environ.get(
    "LAB3_HAI_CSV",
    str(Path(__file__).resolve().parent.parent / "data" / "hai_slice.csv.gz"),
))


# ── Singletons ────────────────────────────────────────────────────────────

engine = ScenarioEngine(session_id=SESSION_ID)
registry = ConnectionRegistry()
event_log = EventLogger(EVENTS_DIR, SESSION_ID)
event_log.log("session_start", {"session_id": SESSION_ID, "seed": engine.state.session_seed})

# HAI replay is optional — if the CSV isn't present the NORMAL_OPS browser
# falls back to client-side placeholder jitter, and we log a warning instead
# of crashing the server.
hai_stream: Optional[HAIStream]
try:
    hai_stream = HAIStream(HAI_CSV_PATH)
    log.info("HAI stream ready: %s", HAI_CSV_PATH)
except FileNotFoundError:
    hai_stream = None
    log.warning("HAI CSV not found at %s — NORMAL_OPS will use client-side jitter", HAI_CSV_PATH)


# ── App ───────────────────────────────────────────────────────────────────

app = FastAPI(title="Lab 3 — Blind Operator", version="0.1.0")

# ── Static student HMI ───────────────────────────────────────────────────
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/style.css", include_in_schema=False)
async def style() -> FileResponse:
    return FileResponse(WEB_DIR / "style.css", media_type="text/css")


@app.get("/app.js", include_in_schema=False)
async def appjs() -> FileResponse:
    return FileResponse(WEB_DIR / "app.js", media_type="application/javascript")


# Instructor dashboard — auth is enforced by the WS/REST endpoints, not here:
# the page itself is just static HTML/JS and will redirect to a token prompt
# if the URL doesn't carry one.
@app.get("/instructor", include_in_schema=False)
async def instructor_page() -> FileResponse:
    return FileResponse(WEB_DIR / "instructor.html")


@app.get("/instructor.css", include_in_schema=False)
async def instructor_css() -> FileResponse:
    return FileResponse(WEB_DIR / "instructor.css", media_type="text/css")


@app.get("/instructor.js", include_in_schema=False)
async def instructor_js() -> FileResponse:
    return FileResponse(WEB_DIR / "instructor.js", media_type="application/javascript")


_pressure_task: Optional[asyncio.Task] = None
_sensor_task: Optional[asyncio.Task] = None


@app.on_event("startup")
async def _startup() -> None:
    global _pressure_task, _sensor_task
    _pressure_task = asyncio.create_task(_pressure_loop())
    if hai_stream is not None:
        _sensor_task = asyncio.create_task(_sensor_loop())


@app.on_event("shutdown")
async def _shutdown() -> None:
    if _pressure_task:
        _pressure_task.cancel()
    if _sensor_task:
        _sensor_task.cancel()
    event_log.log("session_end", {"session_id": SESSION_ID})


# ── Auth ──────────────────────────────────────────────────────────────────

def require_instructor(token: str = Query(...)) -> None:
    if token != INSTRUCTOR_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad token")


# ── REST: instructor ──────────────────────────────────────────────────────

class TieBreakBody(BaseModel):
    group_id: str
    choice: VoteChoice


@app.get("/api/instructor/state", dependencies=[Depends(require_instructor)])
async def instructor_state():
    return JSONResponse(_full_state())


@app.post("/api/instructor/advance", dependencies=[Depends(require_instructor)])
async def instructor_advance():
    try:
        events = engine.advance()
    except EngineError as e:
        raise HTTPException(400, str(e))
    await _process_events(events)
    return {"phase": engine.state.phase.value, "events": [t for t, _ in events]}


@app.post("/api/instructor/inject2", dependencies=[Depends(require_instructor)])
async def instructor_inject2():
    try:
        events = engine.fire_inject2()
    except EngineError as e:
        raise HTTPException(400, str(e))
    await _process_events(events)
    return {"phase": engine.state.phase.value}


@app.post("/api/instructor/break_tie", dependencies=[Depends(require_instructor)])
async def instructor_break_tie(body: TieBreakBody):
    try:
        events = engine.break_tie(body.group_id, body.choice)
    except EngineError as e:
        raise HTTPException(400, str(e))
    await _process_events(events)
    return {"ok": True}


@app.post("/api/instructor/reset_group/{group_id}", dependencies=[Depends(require_instructor)])
async def instructor_reset_group(group_id: str):
    try:
        events = engine.reset_group(group_id)
    except EngineError as e:
        raise HTTPException(400, str(e))
    await _process_events(events)
    return {"ok": True}


class ResetSessionBody(BaseModel):
    confirm: str = Field(..., description="must be the literal string 'RESET'")


@app.post("/api/instructor/reset_session", dependencies=[Depends(require_instructor)])
async def instructor_reset_session(body: ResetSessionBody):
    """Hard-reset the whole scenario without restarting the container.

    - New session_id + seed (in-memory engine).
    - Archive the current JSONL event log to *_archived_<ts>.jsonl and rewire
      the EventLogger to a fresh file under the new session_id.
    - Rewind the HAI cursor so the next NORMAL_OPS replays from row 0.
    - Phase → LOBBY. Groups, students, votes, outcomes all cleared.
    - Fresh state pushed to every connected WebSocket client.
    """
    if body.confirm != "RESET":
        raise HTTPException(400, "confirm payload must be exactly 'RESET'")

    new_session_id = f"session-{int(time.time())}"
    events = engine.reset_session(new_session_id)

    # Archive the old log and start a new one keyed on the new session id.
    archived = event_log.rotate(new_session_id)
    event_log.log("session_start", {
        "session_id": new_session_id,
        "seed": engine.state.session_seed,
        "archived_previous": str(archived) if archived else None,
    })

    # Rewind HAI so NORMAL_OPS plays from the top of the slice.
    if hai_stream is not None:
        hai_stream.rewind()

    # Broadcast: this pushes state_update to all students + a fresh `state`
    # message to instructor dashboards via the existing fan-out path.
    await _process_events(events)
    return {
        "ok": True,
        "session_id": new_session_id,
        "archived_log": str(archived) if archived else None,
    }


# ── WebSocket: student ────────────────────────────────────────────────────

@app.websocket("/ws/group/{group_id}")
async def student_ws(ws: WebSocket, group_id: str):
    await ws.accept()
    student_id: Optional[str] = None
    try:
        # First message must be a join.
        first = await ws.receive_json()
        if first.get("type") != "join":
            await ws.send_json({"type": "error", "error": "first message must be join"})
            await ws.close()
            return

        student_id = first.get("student_id") or str(uuid.uuid4())
        display_name = first.get("display_name", "Anonymous")
        role_str = first.get("role")
        try:
            role = Role(role_str)
        except ValueError:
            await ws.send_json({"type": "error", "error": f"unknown role {role_str!r}"})
            await ws.close()
            return

        try:
            events = engine.join(group_id, student_id, display_name, role)
        except EngineError as e:
            await ws.send_json({"type": "error", "error": str(e)})
            await ws.close()
            return

        registry.add_student(group_id, student_id, ws)
        await _process_events(events)

        # Send current state immediately so the client renders correctly.
        await ws.send_json(_state_update_for(group_id, student_id))

        # Main receive loop — handle votes + pings.
        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type")
            if mtype == "vote":
                try:
                    choice = VoteChoice(msg["choice"])
                except (KeyError, ValueError):
                    await ws.send_json({"type": "error", "error": "bad vote payload"})
                    continue
                try:
                    events = engine.cast_vote(group_id, student_id, choice)
                except EngineError as e:
                    await ws.send_json({"type": "error", "error": str(e)})
                    continue
                await _process_events(events)
            elif mtype == "ping":
                await ws.send_json({"type": "pong"})
            else:
                await ws.send_json({"type": "error", "error": f"unknown type {mtype!r}"})

    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        log.exception("student ws error: %s", e)
    finally:
        if student_id is not None:
            registry.remove_student(group_id, student_id)
            events = engine.disconnect(group_id, student_id)
            await _process_events(events)


# ── WebSocket: instructor ─────────────────────────────────────────────────

@app.websocket("/ws/instructor")
async def instructor_ws(ws: WebSocket, token: str = Query(...)):
    if token != INSTRUCTOR_TOKEN:
        await ws.close(code=4401)
        return
    await ws.accept()
    registry.add_instructor(ws)
    try:
        await ws.send_json({"type": "state", "state": _full_state()})
        while True:
            # Instructor WS is mostly server→client; we just keep it open.
            msg = await ws.receive_json()
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        registry.remove_instructor(ws)


# ── Periodic pressure broadcaster ─────────────────────────────────────────

async def _sensor_loop() -> None:
    """During NORMAL_OPS, advance HAI one row per tick and broadcast to all clients.

    Off phase: still keep the HAI cursor stationary (we *don't* advance the row
    so frozen_sensors stays accurate to the moment of INJECT_1).
    """
    assert hai_stream is not None
    try:
        while True:
            await asyncio.sleep(SENSOR_TICK_SECONDS)
            if engine.state.phase is not Phase.NORMAL_OPS:
                continue
            sensors = hai_stream.next_row()
            # Round to 2 decimals for display; raw floats are noisy.
            rounded = {k: round(v, 2) for k, v in sensors.items()}
            await registry.broadcast_everyone({
                "type": "sensor_tick",
                "sensors": rounded,
            })
    except asyncio.CancelledError:
        return


async def _pressure_loop() -> None:
    """While pressure phases are active, push a tick to all clients."""
    try:
        while True:
            await asyncio.sleep(PRESSURE_TICK_SECONDS)
            if not gauge_visible(engine.state.phase):
                continue
            elapsed = engine.inject2_elapsed_seconds()
            tick = {
                "type": "pressure_tick",
                "phase": engine.state.phase.value,
                "elapsed_seconds": elapsed,
                "groups": {},
            }
            for gid in list(engine.state.groups.keys()):
                # Each group uses a per-group seed so curves are independent.
                seed = (engine.state.session_seed * 1000003) ^ hash(gid)
                p = pressure_mod.pressure_at(elapsed, seed)
                tick["groups"][gid] = {
                    "pressure_bar": round(p, 3),
                    "red_zone": pressure_mod.in_red_zone(p),
                }
            await registry.broadcast_everyone(tick)
    except asyncio.CancelledError:
        return


# ── Helpers ───────────────────────────────────────────────────────────────

def _full_state() -> dict:
    snap = engine.snapshot()
    snap["inject2_elapsed_seconds"] = engine.inject2_elapsed_seconds()
    snap["connected_students_per_group"] = {
        gid: len(registry.students_in_group(gid))
        for gid in engine.state.groups
    }
    return snap


def _state_update_for(group_id: str, student_id: str) -> dict:
    group = engine.state.groups.get(group_id)
    student = group.students.get(student_id) if group else None
    phase = engine.state.phase
    msg = {
        "type": "state_update",
        "phase": phase.value,
        "phase_started_at": engine.state.phase_started_at,
        "group_id": group_id,
        "your_role": student.role.value if student else None,
        "vote_closed": group.vote_closed if group else False,
        "tally": group.vote_tally() if group else None,
        "show_gauge": gauge_visible(phase) and (
            student.role is Role.PLANT_MANAGER if student else False
        ),
        "sensors_streaming": sensors_streaming(phase),
        "frozen_sensors": group.frozen_sensors if group else None,
    }
    if group and group.outcome and phase is Phase.OUTCOME:
        msg["outcome"] = group.outcome.model_dump(mode="json")
    return msg


async def _process_events(events: list[tuple]) -> None:
    """Log + broadcast a batch of engine events."""
    if not events:
        return
    event_log.log_many(events)

    needs_state_push = False
    for etype, payload in events:
        if etype == "phase_advance":
            needs_state_push = True
            # When the ransomware fires, snapshot the last HAI values into every
            # group so the locked HMI keeps showing the moment ops went dark.
            if payload.get("to") == Phase.INJECT_1_RANSOMWARE.value and hai_stream is not None:
                frozen = {k: round(v, 2) for k, v in hai_stream.latest().items()}
                for group in engine.state.groups.values():
                    group.frozen_sensors = frozen
        elif etype == "outcome_resolved":
            needs_state_push = True
        elif etype == "vote_cast":
            # Only push tally update to the group.
            await registry.send_to_group(payload["group_id"], {
                "type": "vote_tally", "tally": payload["tally"],
            })
            await registry.send_to_instructors({"type": "engine_event", "event": etype, "payload": payload})
        elif etype in ("group_join", "reconnect", "disconnect", "group_reset", "vote_unresolved", "vote_closed"):
            await registry.send_to_instructors({"type": "engine_event", "event": etype, "payload": payload})

    if needs_state_push:
        # Push tailored state_update to each student.
        for (gid, sid) in list(registry._students.keys()):  # noqa: SLF001
            await registry.send_to_student(gid, sid, _state_update_for(gid, sid))
        await registry.send_to_instructors({"type": "state", "state": _full_state()})
