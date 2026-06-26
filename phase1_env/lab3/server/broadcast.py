"""
broadcast.py — WebSocket connection registry + fan-out.

Tracks one connection per (group_id, student_id) plus instructor connections.
Provides helpers to push a message to:
  - a single student
  - all students in a group
  - all students in the session
  - all instructors

Failed sends drop the dead socket from the registry. Callers don't have to
worry about cleanup.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Iterable

from fastapi import WebSocket

log = logging.getLogger("lab3.broadcast")


class ConnectionRegistry:
    def __init__(self) -> None:
        # (group_id, student_id) -> WebSocket
        self._students: dict[tuple[str, str], WebSocket] = {}
        # set of instructor sockets
        self._instructors: set[WebSocket] = set()

    # ── Registration ───────────────────────────────────────────────────────

    def add_student(self, group_id: str, student_id: str, ws: WebSocket) -> None:
        self._students[(group_id, student_id)] = ws

    def remove_student(self, group_id: str, student_id: str) -> None:
        self._students.pop((group_id, student_id), None)

    def add_instructor(self, ws: WebSocket) -> None:
        self._instructors.add(ws)

    def remove_instructor(self, ws: WebSocket) -> None:
        self._instructors.discard(ws)

    def students_in_group(self, group_id: str) -> list[str]:
        return [sid for (gid, sid) in self._students if gid == group_id]

    # ── Send ───────────────────────────────────────────────────────────────

    async def send_to_student(self, group_id: str, student_id: str, msg: dict) -> None:
        ws = self._students.get((group_id, student_id))
        if ws is None:
            return
        await self._safe_send(ws, msg, lambda: self.remove_student(group_id, student_id))

    async def send_to_group(self, group_id: str, msg: dict) -> None:
        targets = [(k, ws) for k, ws in self._students.items() if k[0] == group_id]
        await self._fan_out(targets, msg, student=True)

    async def send_to_all_students(self, msg: dict) -> None:
        targets = list(self._students.items())
        await self._fan_out(targets, msg, student=True)

    async def send_to_instructors(self, msg: dict) -> None:
        targets = [(None, ws) for ws in list(self._instructors)]
        await self._fan_out(targets, msg, student=False)

    async def broadcast_everyone(self, msg: dict) -> None:
        await asyncio.gather(
            self.send_to_all_students(msg),
            self.send_to_instructors(msg),
        )

    # ── Internals ──────────────────────────────────────────────────────────

    async def _fan_out(
        self,
        targets: Iterable[tuple],
        msg: dict,
        *,
        student: bool,
    ) -> None:
        async def one(key, ws):
            await self._safe_send(
                ws,
                msg,
                cleanup=(lambda: self.remove_student(*key)) if student else (lambda: self.remove_instructor(ws)),
            )

        await asyncio.gather(*(one(k, ws) for k, ws in targets), return_exceptions=True)

    async def _safe_send(self, ws: WebSocket, msg: dict, cleanup) -> None:
        try:
            await ws.send_json(msg)
        except Exception as e:  # noqa: BLE001 — any send failure → drop
            log.debug("websocket send failed (%s); dropping connection", e)
            try:
                cleanup()
            except Exception:
                pass
