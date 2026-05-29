"""
frame.py — The universal wire format for the data diode.

This is the exact binary layout that crosses the diode.
Every component (OT proxy, FPGA, IT proxy) must agree on this.

FRAME LAYOUT (24 bytes for a single sensor reading):
┌────────┬───────┬────────┬─────┬───────────────────────┬────────┐
│ SYNC   │ SEQ   │ LEN    │ TTL │ PAYLOAD (11 bytes)    │ CRC-32 │
│ 2B     │ 4B    │ 2B     │ 1B  │ ts(4)+tag(2)+val(4)+q(1) │ 4B  │
└────────┴───────┴────────┴─────┴───────────────────────┴────────┘
"""

import struct
import zlib

# The sync word — FPGA scans the byte stream for this pattern
SYNC_WORD = 0xAA55

# Quality codes — what the sensor is reporting about its own health
QUALITY_GOOD       = 0x00
QUALITY_UNCERTAIN  = 0x01
QUALITY_BAD        = 0x02
QUALITY_COMM_FAIL  = 0xFF


def pack_sensor_struct(timestamp: int, tag_id: int, value: float, quality: int) -> bytes:
    """
    Pack a single sensor reading into the 11-byte binary struct.

    This is the PAYLOAD — the actual data the customer cares about.

    Args:
        timestamp: UNIX epoch seconds (4 bytes, unsigned)
        tag_id:    sensor identifier from lookup table (2 bytes, unsigned)
        value:     the reading as a float (4 bytes, IEEE 754)
        quality:   one of the QUALITY_* constants (1 byte)

    Returns:
        11 bytes: the packed sensor struct
    """
    # '!' = network byte order (big-endian) — no ambiguity between machines
    # 'I' = uint32 (timestamp)
    # 'H' = uint16 (tag_id)
    # 'f' = float32 (value)
    # 'B' = uint8 (quality)
    return struct.pack('!IHfB', timestamp, tag_id, value, quality)


def unpack_sensor_struct(data: bytes) -> dict:
    """
    Unpack the 11-byte struct back into human-readable fields.
    Used by the IT proxy after receiving a valid frame.
    """
    timestamp, tag_id, value, quality = struct.unpack('!IHfB', data)
    return {
        'timestamp': timestamp,
        'tag_id': tag_id,
        'value': round(value, 4),  # float32 has rounding artifacts
        'quality': quality,
    }


def build_frame(seq: int, ttl: int, payload: bytes) -> bytes:
    """
    Wrap a payload in the full frame envelope.

    This is what actually goes on the wire:
    SYNC (2) + SEQ (4) + LEN (2) + TTL (1) + PAYLOAD (variable) + CRC32 (4)

    Args:
        seq:     sequence number (monotonically increasing per reading)
        ttl:     copy number (3 = first copy, 2 = second, 1 = last)
        payload: the 11-byte sensor struct (or any payload up to 1024 bytes)

    Returns:
        The complete frame as bytes
    """
    # Pack the header
    header = struct.pack('!HI H B',
        SYNC_WORD,          # 2 bytes: sync marker
        seq,                # 4 bytes: sequence number
        len(payload),       # 2 bytes: payload length
        ttl,                # 1 byte:  copy number
    )

    # CRC covers everything EXCEPT sync and CRC itself
    # Why not sync? Because sync is just for alignment — not data.
    crc_data = header[2:] + payload   # SEQ + LEN + TTL + PAYLOAD
    crc = zlib.crc32(crc_data) & 0xFFFFFFFF   # ensure unsigned 32-bit

    crc_bytes = struct.pack('!I', crc)

    return header + payload + crc_bytes


def parse_frame(data: bytes) -> dict | None:
    """
    Parse a complete frame from bytes. Returns None if CRC check fails.

    Used by:
    - FPGA sim: to verify CRC before forwarding
    - IT proxy: to extract the payload after deduplication
    """
    if len(data) < 13:  # minimum: 2+4+2+1+0+4 = 13 bytes (empty payload)
        return None

    # Read header
    sync, seq, payload_len, ttl = struct.unpack('!HIHB', data[:9])

    if sync != SYNC_WORD:
        return None

    expected_total = 9 + payload_len + 4  # header + payload + CRC
    if len(data) < expected_total:
        return None

    payload = data[9 : 9 + payload_len]
    received_crc = struct.unpack('!I', data[9 + payload_len : 9 + payload_len + 4])[0]

    # Verify CRC — same calculation as build_frame
    crc_data = data[2 : 9 + payload_len]   # SEQ + LEN + TTL + PAYLOAD
    computed_crc = zlib.crc32(crc_data) & 0xFFFFFFFF

    if computed_crc != received_crc:
        return None  # corrupted — drop silently, just like real FPGA

    return {
        'seq': seq,
        'ttl': ttl,
        'payload_len': payload_len,
        'payload': payload,
        'crc': received_crc,
        'raw': data[:expected_total],      # the complete frame bytes
        'total_len': expected_total,
    }


# ── Frame size constants ─────────────────────────────────────
HEADER_SIZE  = 9    # SYNC(2) + SEQ(4) + LEN(2) + TTL(1)
CRC_SIZE     = 4
SENSOR_STRUCT_SIZE = 11
FRAME_SIZE   = HEADER_SIZE + SENSOR_STRUCT_SIZE + CRC_SIZE   # 24 bytes
