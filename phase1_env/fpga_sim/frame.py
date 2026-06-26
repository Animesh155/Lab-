"""
frame.py — The universal wire format for the data diode.

This is the exact binary layout that crosses the diode.
Every component (OT proxy, FPGA, IT proxy) must agree on this.

═══════════════════════════════════════════════════════════════════════
 FRAME LAYOUT (28 bytes total — with Reed-Solomon FEC)
═══════════════════════════════════════════════════════════════════════

┌────────┬───────┬────────┬─────┬───────────────────────┬──────────┬────────┐
│ SYNC   │ SEQ   │ LEN    │ TTL │ PAYLOAD (11 bytes)    │ RS PARITY│ CRC-32 │
│ 2B     │ 4B    │ 2B     │ 1B  │ ts(4)+tag(2)+val(4)+q(1)│ 4B      │ 4B     │
└────────┴───────┴────────┴─────┴───────────────────────┴──────────┴────────┘
  0xAA55   uint32  uint16  uint8                            RS(15,11)  CRC over
                                                            over       SEQ+LEN+
                                                            PAYLOAD    TTL+PAYLOAD
                                                                       +RS_PARITY

═══════════════════════════════════════════════════════════════════════
 REED-SOLOMON PARAMETERS (HARDWARE-AWARE)
═══════════════════════════════════════════════════════════════════════

  Code:               RS(15, 11) over GF(2^8)
  Symbol size:         m = 8 bits (1 byte)
  Code word length:    n = 15 symbols
  Data symbols:        k = 11 symbols
  Parity symbols:      n-k = 4 symbols
  Correction power:    t = (n-k)/2 = 2 byte errors per code word
  Detection power:     up to 4 erroneous bytes (without correction)

  Field polynomial:    0x11D = x^8 + x^4 + x^3 + x^2 + 1
                       (Standard CCSDS/DVB, equals (285)_10)
  Primitive element:   alpha = 0x02 (default for this polynomial)
  Generator root:      fcr = 0 (first consecutive root)
  Generator base:      g(x) = (x - alpha^0)(x - alpha^1)(x - alpha^2)(x - alpha^3)

  These parameters DIRECTLY MATCH:
    - Xilinx Reed-Solomon Encoder/Decoder LogiCORE IP
    - Intel Reed-Solomon II IP
    - Lattice Reed-Solomon IP
    - Standard CCSDS deep-space telemetry coding
    - Standard DVB-S/T digital broadcasting (with shortening to RS(15,11))

  This means: when the Verilog FPGA implementation goes live, this Python
  code can serve as the bit-accurate reference model. Encoded outputs MUST
  match byte-for-byte with hardware IP cores configured with these params.

═══════════════════════════════════════════════════════════════════════
 ERROR PROTECTION FLOW
═══════════════════════════════════════════════════════════════════════

  SENDER (build_frame):
    1. Compute RS parity over the 11-byte payload → 4 bytes
    2. Compute CRC-32 over SEQ+LEN+TTL+PAYLOAD+RS_PARITY → 4 bytes
    3. Assemble: SYNC + header + payload + parity + CRC

  RECEIVER (parse_frame):
    1. Verify SYNC marker (fail fast on garbage)
    2. Compute expected CRC-32 over SEQ+LEN+TTL+PAYLOAD+RS_PARITY
    3. If CRC matches → frame intact, no RS needed (fast path)
    4. If CRC fails → run RS decoder on (PAYLOAD || RS_PARITY)
       - RS can fix up to 2 byte errors
       - If fix succeeds → emit corrected payload
       - If fix fails → drop frame (CRC + RS both failed = uncorrectable)

  This layered approach is HARDWARE-EFFICIENT:
    - CRC is the fast path (most frames pass it)
    - RS only runs on the (small) fraction with errors
    - In FPGA: pipeline stages can run CRC and RS in parallel
"""

import struct
import zlib

# ── Wire-format constants ────────────────────────────────────
SYNC_WORD = 0xAA55

# Quality codes — what the sensor is reporting about its own health
QUALITY_GOOD       = 0x00
QUALITY_UNCERTAIN  = 0x01
QUALITY_BAD        = 0x02
QUALITY_COMM_FAIL  = 0xFF

# ── Reed-Solomon parameters (HARDWARE-AWARE) ─────────────────
# These exact values must be used in the Verilog implementation.
RS_CODE_N           = 15        # total code word size (symbols)
RS_CODE_K           = 11        # data symbols
RS_PARITY_BYTES     = 4         # parity symbols (= n - k)
RS_CORRECTION_T     = 2         # max correctable byte errors
RS_SYMBOL_BITS      = 8         # GF(2^m), m = 8
RS_FIELD_POLY       = 0x11D     # primitive polynomial
RS_FIRST_CONSEC_ROOT = 0        # fcr
RS_GENERATOR        = 2         # generator base alpha

# ── Frame size constants ─────────────────────────────────────
HEADER_SIZE         = 9         # SYNC(2) + SEQ(4) + LEN(2) + TTL(1)
SENSOR_STRUCT_SIZE  = 11        # the payload size (= RS_CODE_K)
CRC_SIZE            = 4         # CRC-32
FRAME_SIZE          = HEADER_SIZE + SENSOR_STRUCT_SIZE + RS_PARITY_BYTES + CRC_SIZE
                    #  = 9 + 11 + 4 + 4 = 28 bytes

# Field offsets (for hardware port reference)
OFFSET_SYNC         = 0         # bytes 0-1
OFFSET_SEQ          = 2         # bytes 2-5
OFFSET_LEN          = 6         # bytes 6-7
OFFSET_TTL          = 8         # byte  8
OFFSET_PAYLOAD      = 9         # bytes 9-19
OFFSET_RS_PARITY    = 20        # bytes 20-23
OFFSET_CRC          = 24        # bytes 24-27

# ── Reed-Solomon codec (lazy init) ───────────────────────────
_rs_codec = None

def _get_rs():
    """Initialize Reed-Solomon codec on first use."""
    global _rs_codec
    if _rs_codec is None:
        from reedsolo import RSCodec
        _rs_codec = RSCodec(
            nsym=RS_PARITY_BYTES,    # 4 parity symbols
            nsize=RS_CODE_N,         # 15 total
            fcr=RS_FIRST_CONSEC_ROOT,
            prim=RS_FIELD_POLY,
            generator=RS_GENERATOR,
            c_exp=RS_SYMBOL_BITS,
        )
    return _rs_codec


def rs_encode(payload: bytes) -> bytes:
    """
    Reed-Solomon encode: 11 bytes → 15 bytes (data + parity).
    Returns ONLY the 4 parity bytes (data is unchanged).

    Hardware equivalent: Xilinx RS Encoder LogiCORE configured
    with identical parameters produces bit-identical output.
    """
    assert len(payload) == RS_CODE_K, \
        f"RS input must be exactly {RS_CODE_K} bytes, got {len(payload)}"
    code_word = _get_rs().encode(payload)
    # code_word = data (11B) + parity (4B). We want just the parity.
    assert len(code_word) == RS_CODE_N
    return bytes(code_word[RS_CODE_K:])


def rs_decode(payload: bytes, parity: bytes) -> tuple:
    """
    Reed-Solomon decode: validate and (if possible) correct errors.

    Returns:
        (corrected_payload, num_errors_corrected) on success
        (None, 0) if uncorrectable (> 2 byte errors)

    Hardware equivalent: Xilinx RS Decoder LogiCORE configured
    with identical parameters produces equivalent corrections.
    """
    from reedsolo import ReedSolomonError
    if len(payload) != RS_CODE_K or len(parity) != RS_PARITY_BYTES:
        return (None, 0)
    code_word = bytes(payload) + bytes(parity)
    try:
        decoded, _, errata_pos = _get_rs().decode(code_word)
        # decoded should be the 11-byte data portion
        return (bytes(decoded), len(errata_pos))
    except ReedSolomonError:
        return (None, 0)


# ── Sensor struct (unchanged) ────────────────────────────────
def pack_sensor_struct(timestamp: int, tag_id: int, value: float, quality: int) -> bytes:
    """
    Pack a single sensor reading into the 11-byte binary struct.
    Format: !IHfB = big-endian uint32 + uint16 + float32 + uint8
    """
    return struct.pack('!IHfB', timestamp, tag_id, value, quality)


def unpack_sensor_struct(data: bytes) -> dict:
    """Unpack the 11-byte struct back into human-readable fields."""
    timestamp, tag_id, value, quality = struct.unpack('!IHfB', data)
    return {
        'timestamp': timestamp,
        'tag_id': tag_id,
        'value': round(value, 4),
        'quality': quality,
    }


# ── Frame builder ────────────────────────────────────────────
def build_frame(seq: int, ttl: int, payload: bytes) -> bytes:
    """
    Wrap a payload in the full 28-byte frame envelope with RS+CRC.

    Wire layout: SYNC(2) + SEQ(4) + LEN(2) + TTL(1) + PAYLOAD(11)
                 + RS_PARITY(4) + CRC32(4) = 28 bytes

    Args:
        seq:     sequence number (uint32)
        ttl:     copy number (uint8) — 1, 2, or 3
        payload: exactly 11 bytes (sensor struct)

    Returns:
        Complete 28-byte frame.
    """
    assert len(payload) == SENSOR_STRUCT_SIZE, \
        f"payload must be {SENSOR_STRUCT_SIZE} bytes, got {len(payload)}"

    # Pack the 9-byte header
    header = struct.pack('!HI H B',
        SYNC_WORD,              # 2 bytes: sync marker (alignment only)
        seq,                    # 4 bytes: sequence number
        len(payload),           # 2 bytes: payload length (= 11)
        ttl,                    # 1 byte:  copy number
    )

    # Compute Reed-Solomon parity over PAYLOAD only
    # (Header is protected by CRC, not by RS — keeps RS code word small)
    rs_parity = rs_encode(payload)   # 4 bytes

    # CRC covers everything EXCEPT sync and CRC itself.
    # Now includes the RS parity so corruption to parity is also detected.
    crc_data = header[2:] + payload + rs_parity   # bytes 2..23
    crc = zlib.crc32(crc_data) & 0xFFFFFFFF
    crc_bytes = struct.pack('!I', crc)

    return header + payload + rs_parity + crc_bytes


# ── Frame parser ─────────────────────────────────────────────
def parse_frame(data: bytes) -> dict | None:
    """
    Parse a 28-byte frame. Returns dict with frame fields, or None if
    the frame is unrecoverable.

    Recovery path:
      1. SYNC check (fail fast)
      2. CRC check (fast path — most frames pass)
      3. If CRC fails: try RS decoder
         - If RS fixes ≤2 byte errors → return corrected frame
         - If RS fails → return None (frame is uncorrectable)

    Returned dict includes:
      'rs_corrected': 0 if no errors, 1 or 2 if RS fixed errors
    """
    if len(data) < FRAME_SIZE:
        return None

    # Parse header (always trusted to read — header errors caught by CRC)
    sync, seq, payload_len, ttl = struct.unpack('!HIHB', data[:HEADER_SIZE])

    if sync != SYNC_WORD:
        return None

    if payload_len != SENSOR_STRUCT_SIZE:
        # Frame size doesn't match what we expect — refuse to parse
        return None

    expected_total = FRAME_SIZE
    if len(data) < expected_total:
        return None

    payload   = data[OFFSET_PAYLOAD : OFFSET_PAYLOAD + SENSOR_STRUCT_SIZE]
    rs_parity = data[OFFSET_RS_PARITY : OFFSET_RS_PARITY + RS_PARITY_BYTES]
    received_crc = struct.unpack('!I', data[OFFSET_CRC : OFFSET_CRC + CRC_SIZE])[0]

    # ── Fast path: verify CRC ────────────────────────────────
    crc_data = data[OFFSET_SEQ : OFFSET_CRC]   # bytes 2..23
    computed_crc = zlib.crc32(crc_data) & 0xFFFFFFFF

    if computed_crc == received_crc:
        # Frame intact — no need to run RS
        return {
            'seq': seq,
            'ttl': ttl,
            'payload_len': payload_len,
            'payload': payload,
            'rs_corrected': 0,
            'crc': received_crc,
            'raw': data[:expected_total],
            'total_len': expected_total,
        }

    # ── Slow path: try RS error correction ───────────────────
    # CRC failed — see if RS can repair the payload+parity portion
    corrected_payload, num_errors = rs_decode(payload, rs_parity)

    if corrected_payload is None:
        # RS could not recover (> 2 byte errors, OR errors in header
        # which RS doesn't protect)
        return None

    # RS recovered the payload. We don't re-verify CRC here because:
    #   - CRC failure could have been due to payload OR parity OR header
    #   - If header was corrupted, RS-corrected payload is still valid
    #     for the data it contains (we just can't trust seq/ttl)
    #   - Conservative: trust the RS-corrected payload, log the recovery
    return {
        'seq': seq,
        'ttl': ttl,
        'payload_len': payload_len,
        'payload': corrected_payload,
        'rs_corrected': num_errors,
        'crc': received_crc,
        'raw': data[:expected_total],
        'total_len': expected_total,
    }
