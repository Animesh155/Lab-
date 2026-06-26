"""
events.py — Append-only JSONL event log.

One file per session at events/{session_id}.jsonl. Every line is a JSON object:

    {"ts": "...", "type": "...", "payload": {...}}

The debrief tool reads this file to render per-group timelines and class-wide
vote distribution.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


class EventLogger:
    """Append-only JSONL writer. Sync I/O is fine — events are infrequent."""

    def __init__(self, events_dir: Path | str, session_id: str) -> None:
        self.events_dir = Path(events_dir)
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.events_dir / f"{session_id}.jsonl"
        self.session_id = session_id

    def log(self, event_type: str, payload: dict) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "type": event_type,
            "payload": payload,
        }
        line = json.dumps(record, ensure_ascii=False, default=str)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def log_many(self, events: list[tuple[str, dict]]) -> None:
        for event_type, payload in events:
            self.log(event_type, payload)

    def archive(self) -> Path | None:
        """Move current log to *_archived_{ts}.jsonl. Used on session reset."""
        if not self.path.exists():
            return None
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        archive_path = self.events_dir / f"{self.session_id}_archived_{ts}.jsonl"
        os.replace(self.path, archive_path)
        return archive_path

    def rotate(self, new_session_id: str) -> Path | None:
        """Archive current log and rewire to a fresh file. Returns archive path."""
        archived = self.archive()
        self.session_id = new_session_id
        self.path = self.events_dir / f"{new_session_id}.jsonl"
        return archived
