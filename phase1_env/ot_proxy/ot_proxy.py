"""
ot_proxy.py — OT-Side Proxy (multi-adapter version)

The bridge between the industrial world and the data diode.

What this does:
  1. POLL:        Fetches sensor data via PLUGGABLE ADAPTERS (Modbus, OPC UA, etc.)
  2. NORMALIZE:   Adapters convert protocol-specific responses into universal struct
  3. FRAME:       Wraps in wire format with SYNC, SEQ, CRC
  4. COPY:        Generates 3 copies (TTL = 3, 2, 1)
  5. INTERLEAVE:  Spreads copies apart so one burst can't kill all copies
  6. SEND:        UDP datagrams to the FPGA (one-way, no response expected)

Adapter selection:
  Set ADAPTER environment variable:
    ADAPTER=modbus   → uses Modbus TCP adapter
    ADAPTER=http     → legacy Node-RED HTTP/JSON path (kept for compatibility)
"""

import time
import socket
import urllib.request
import json
import collections
import os
import struct
from frame import (
    pack_sensor_struct, build_frame,
    QUALITY_GOOD, QUALITY_COMM_FAIL
)

# ── Heartbeat constants ───────────────────────────────────────
# Reserved tag_id for "I'm alive" frames. The IT proxy treats any
# frame with this tag as a heartbeat (not a sensor reading).
# 0xFFFF is the top of uint16 space — well clear of real sensor tags
# (which use 0x0001-0x010F today).
HEARTBEAT_TAG_ID = 0xFFFF

# ── Configuration ─────────────────────────────────────────────
ADAPTER_TYPE      = os.environ.get('ADAPTER', 'modbus').lower()
FPGA_HOST         = os.environ.get('FPGA_HOST', 'fpga-sim')
FPGA_PORT         = int(os.environ.get('FPGA_PORT', '5000'))
POLL_INTERVAL     = float(os.environ.get('POLL_INTERVAL', '1.0'))
NUM_COPIES        = int(os.environ.get('NUM_COPIES', '3'))
INTERLEAVE_DEPTH  = int(os.environ.get('INTERLEAVE_DEPTH', '3'))

# Modbus adapter config
MODBUS_HOST       = os.environ.get('MODBUS_HOST', 'plc-modbus')
MODBUS_PORT       = int(os.environ.get('MODBUS_PORT', '502'))

# Legacy HTTP adapter config (for backward compatibility with Node-RED)
SENSOR_POLL_URL   = os.environ.get('SENSOR_URL', 'http://ot-simulator:1880/api/plc-data')

# Legacy TAG_MAP for HTTP adapter
TAG_MAP_HTTP = {
    'temperature': 0x0001,
    'pressure':    0x0002,
    'status':      0x0003,
}


# ── Legacy HTTP Adapter (kept for backward compatibility) ─────
def poll_http_json() -> list[dict]:
    """Original Node-RED HTTP/JSON poll. Used if ADAPTER=http."""
    try:
        req = urllib.request.Request(SENSOR_POLL_URL)
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"[POLL] HTTP failed: {e}")
        return []

    timestamp = int(time.time())
    readings = []
    tags = data.get('tags', {})

    if 'temperature' in tags:
        readings.append({
            'timestamp': timestamp, 'tag_id': TAG_MAP_HTTP['temperature'],
            'value': float(tags['temperature']), 'quality': QUALITY_GOOD,
            'name': 'temperature',
        })
    if 'pressure' in tags:
        readings.append({
            'timestamp': timestamp, 'tag_id': TAG_MAP_HTTP['pressure'],
            'value': float(tags['pressure']), 'quality': QUALITY_GOOD,
            'name': 'pressure',
        })
    if 'status' in tags:
        status_val = 0.0 if tags['status'] == 'RUNNING' else 1.0
        readings.append({
            'timestamp': timestamp, 'tag_id': TAG_MAP_HTTP['status'],
            'value': status_val, 'quality': QUALITY_GOOD,
            'name': 'status',
        })
    return readings


# ── Interleave Buffer ─────────────────────────────────────────
class InterleaveBuffer:
    """
    Manages interleaving of frame copies across multiple lanes.

    For multi-sensor poll cycles (which is our case — Modbus reads 15 at once),
    this naturally spaces copies of the same frame apart by num_sensors positions.
    See dequeue() docstring for details.
    """

    def __init__(self, num_copies: int, depth: int):
        self.num_copies = num_copies
        self.depth = depth
        self.lanes = [collections.deque() for _ in range(num_copies)]

    def enqueue(self, seq: int, payload: bytes):
        for i in range(self.num_copies):
            ttl = self.num_copies - i
            frame = build_frame(seq, ttl, payload)
            self.lanes[i].append(frame)

    def dequeue(self) -> bytes | None:
        """
        Drain lane-by-lane. With N sensors enqueued per cycle:
          lane[0] has [F0.a, F1.a, F2.a ... FN.a]
          lane[1] has [F0.b, F1.b, F2.b ... FN.b]
          lane[2] has [F0.c, F1.c, F2.c ... FN.c]

        Output: F0.a F1.a F2.a ... FN.a | F0.b F1.b ... FN.b | F0.c F1.c ... FN.c
        Result: copies of the same SEQ are N positions apart in time.
        """
        for lane in self.lanes:
            if lane:
                return lane.popleft()
        return None

    def pending(self) -> int:
        return sum(len(lane) for lane in self.lanes)


# ── Adapter Factory ──────────────────────────────────────────
def create_adapter():
    """Build the adapter specified by ADAPTER env var."""
    if ADAPTER_TYPE == 'modbus':
        from adapters.modbus_adapter import ModbusAdapter
        adapter = ModbusAdapter(host=MODBUS_HOST, port=MODBUS_PORT)
        print(f"[ADAPTER] Modbus TCP → {MODBUS_HOST}:{MODBUS_PORT}")
        return adapter
    elif ADAPTER_TYPE == 'http':
        print(f"[ADAPTER] HTTP/JSON (legacy) → {SENSOR_POLL_URL}")
        return None   # use legacy poll_http_json()
    else:
        raise ValueError(f"Unknown ADAPTER type: {ADAPTER_TYPE}")


# ── Main Loop ─────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  OT-SIDE PROXY — Multi-Adapter Data Diode Sender")
    print("=" * 60)
    print(f"  Adapter:     {ADAPTER_TYPE}")
    print(f"  Sending to:  {FPGA_HOST}:{FPGA_PORT} (UDP)")
    print(f"  Copies:      {NUM_COPIES}x")
    print(f"  Interval:    {POLL_INTERVAL}s")
    print("=" * 60)

    # Build the adapter
    adapter = create_adapter()

    # Wait for adapter to be ready
    print("[INIT] Waiting for sensor source to come up...")
    while True:
        if adapter is None:
            # HTTP adapter — try a request
            try:
                urllib.request.urlopen(SENSOR_POLL_URL, timeout=2.0)
                print("[INIT] HTTP source is up!")
                break
            except Exception:
                time.sleep(2)
        else:
            # Modbus adapter — try to connect
            if adapter.connect():
                print("[INIT] Modbus PLC is up!")
                break
            time.sleep(2)

    # UDP socket — send only
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    buffer = InterleaveBuffer(NUM_COPIES, INTERLEAVE_DEPTH)
    seq = 0
    total_readings = 0

    # Heartbeat state — uptime starts now, in monotonic seconds.
    # We use monotonic so NTP adjustments / system clock changes don't
    # mess up the heartbeat's "I've been running this long" value.
    start_time_monotonic = time.monotonic()

    while True:
        # ── Step 1: Poll ──────────────────────────────────────
        if adapter is None:
            readings = poll_http_json()
        else:
            readings = adapter.poll()

        # ── Step 1b: Generate heartbeat ───────────────────────
        # Sent EVERY cycle, regardless of whether sensors responded.
        # Quality reflects whether the adapter is healthy:
        #   - GOOD if we got sensor readings this cycle
        #   - COMM_FAIL if poll returned nothing or all were COMM_FAIL
        # IT side can use this to distinguish "OT alive but PLC down"
        # from "OT proxy dead entirely" (no heartbeat at all).
        uptime_s = time.monotonic() - start_time_monotonic
        adapter_healthy = bool(readings) and any(
            r.get('quality', QUALITY_COMM_FAIL) == QUALITY_GOOD
            for r in readings
        )
        heartbeat = {
            'timestamp': int(time.time()),
            'tag_id':    HEARTBEAT_TAG_ID,
            'value':     float(uptime_s),
            'quality':   QUALITY_GOOD if adapter_healthy else QUALITY_COMM_FAIL,
            'name':      '__heartbeat__',
        }
        # Append after sensor readings so heartbeat goes through
        # the same frame builder + interleave + 3-copy path as data.
        readings = list(readings) + [heartbeat]

        # ── Step 2-4: Pack, Frame, Copy ───────────────────────
        for reading in readings:
            payload = pack_sensor_struct(
                reading['timestamp'],
                reading['tag_id'],
                reading['value'],
                reading['quality'],
            )
            buffer.enqueue(seq, payload)
            seq += 1

        # ── Step 5-6: Interleave and Send ─────────────────────
        sent_count = 0
        while buffer.pending() > 0:
            frame = buffer.dequeue()
            if frame:
                sock.sendto(frame, (FPGA_HOST, FPGA_PORT))
                sent_count += 1
                time.sleep(0.01)   # small wire-time gap

        if readings:
            total_readings += len(readings)
            # Pull names from the first few readings for a useful summary
            sample = ", ".join(
                f"{r.get('name','?')}={r['value']:.1f}"
                for r in readings[:3]
            )
            print(f"[TX] SEQ {seq - len(readings)}-{seq - 1} | "
                  f"{len(readings)} readings | {sent_count} frames sent | "
                  f"sample: {sample}")

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    main()
