"""smoke_hai.py — verify real HAI sensors stream and freeze correctly."""

from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx
import websockets

BASE = os.environ.get("LAB3_BASE_URL", "http://127.0.0.1:8080")
WS = BASE.replace("http", "ws")
TOKEN = os.environ.get("LAB3_INSTRUCTOR_TOKEN", "test123")

EXPECTED_SENSORS = {
    "s_reactor1_pressure", "s_reactor1_temp", "s_feed_flow", "s_tank_level",
    "s_outlet_flow", "s_pump_a", "s_pump_b", "s_valve",
}


def ok(s): print(f"  ✓ {s}", flush=True)
def fail(s): print(f"  ✗ {s}", flush=True); sys.exit(1)


async def post(client, path):
    r = await client.post(f"{BASE}{path}", params={"token": TOKEN})
    r.raise_for_status()
    return r.json()


async def main():
    print("\n=== HAI sensor smoke test ===\n", flush=True)
    async with httpx.AsyncClient(timeout=10.0) as client:
        ws = await websockets.connect(f"{WS}/ws/group/g9")
        await ws.send(json.dumps({
            "type": "join",
            "student_id": "stu_hai_test",
            "display_name": "Hai Tester",
            "role": "PLANT_MANAGER",
        }))
        inbox = []

        async def reader():
            try:
                async for raw in ws:
                    inbox.append(json.loads(raw))
            except Exception:
                pass

        t = asyncio.create_task(reader())
        await asyncio.sleep(0.3)
        ok("connected and joined as Plant Manager")

        # Advance LOBBY -> BRIEFING -> NORMAL_OPS
        await post(client, "/api/instructor/advance")
        await post(client, "/api/instructor/advance")
        await asyncio.sleep(2.0)
        ticks = [m for m in inbox if m.get("type") == "sensor_tick"]
        if len(ticks) < 2:
            fail(f"expected >=2 sensor_ticks in NORMAL_OPS, got {len(ticks)}")
        first = ticks[0]["sensors"]
        last = ticks[-1]["sensors"]
        missing = EXPECTED_SENSORS - set(first)
        if missing:
            fail(f"sensor_tick missing keys: {missing}")
        ok(f"got {len(ticks)} sensor_ticks with all 8 sensors")
        ok(f"  reactor pressure: first={first['s_reactor1_pressure']} bar  last={last['s_reactor1_pressure']} bar")
        ok(f"  reactor temp:     first={first['s_reactor1_temp']} °C   last={last['s_reactor1_temp']} °C")
        ok(f"  feed flow:        first={first['s_feed_flow']} L/min  last={last['s_feed_flow']} L/min")

        # Trigger ransomware — should freeze sensors
        last_pressure_before_lock = last["s_reactor1_pressure"]
        await post(client, "/api/instructor/advance")  # NORMAL_OPS -> INJECT_1
        await asyncio.sleep(0.5)

        # Look for the state_update at INJECT_1 with frozen_sensors
        injected = [m for m in inbox if m.get("type") == "state_update" and m.get("phase") == "INJECT_1_RANSOMWARE"]
        if not injected:
            fail("no state_update for INJECT_1_RANSOMWARE")
        frozen = injected[-1].get("frozen_sensors")
        if not frozen:
            fail(f"no frozen_sensors in state_update: keys={list(injected[-1].keys())}")
        if abs(frozen["s_reactor1_pressure"] - last_pressure_before_lock) > 0.5:
            fail(f"frozen pressure {frozen['s_reactor1_pressure']} far from pre-lock {last_pressure_before_lock}")
        ok(f"frozen_sensors captured at lock: pressure={frozen['s_reactor1_pressure']} bar")

        # After INJECT_1, NO more sensor_ticks should arrive
        before_count = len(ticks)
        await asyncio.sleep(2.0)
        new_ticks = [m for m in inbox if m.get("type") == "sensor_tick"]
        if len(new_ticks) != before_count:
            fail(f"sensor_ticks continued after lock: {len(new_ticks) - before_count} extras")
        ok("sensor_ticks correctly stopped after ransomware")

        await ws.close()
        t.cancel()

    print("\n=== ALL HAI SMOKE TESTS PASSED ✓ ===\n", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
