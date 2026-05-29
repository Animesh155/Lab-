"""
replayer.py — Attack PCAP Replayer

Reads a PCAP file from the Edge-IIoTset dataset and replays its packet
payloads as UDP datagrams aimed at our diode's input port (fpga-sim:5000).

This simulates an attacker on the OT-side network sending crafted packets
at the diode gateway. We then observe:
  - Does the FPGA's CRC validation reject them?
  - Does the IT side stay alive?
  - Does normal traffic continue unaffected?

Configuration via environment variables:
  ATTACK_PCAP       — path to the PCAP file inside the container
  TARGET_HOST       — where to send the replayed packets (default: fpga-sim)
  TARGET_PORT       — target port (default: 5000)
  REPLAY_RATE       — speed multiplier; 1.0 = real-time, 100.0 = 100x faster
  MAX_PACKETS       — limit replay to N packets (0 = unlimited)
  LOOP              — restart from beginning when PCAP ends (default: false)
  STARTUP_DELAY     — seconds to wait before starting (lets other services boot)

Why scapy:
  PCAP parsing is annoying without a library.
  Scapy reads, lets us extract payload, and lets us forge new packets.
  We're NOT injecting raw L2/L3 packets (would need root + CAP_NET_RAW);
  instead we extract the payload bytes and send them via a plain UDP socket.
  This matches the realistic threat: compromised OT host sending UDP at diode.
"""

import os
import time
import socket
import logging
from scapy.all import PcapReader, IP, TCP, UDP, Raw


# ── Configuration ─────────────────────────────────────────────
ATTACK_PCAP    = os.environ.get('ATTACK_PCAP', '/attacks/MITM_attack.pcap')
TARGET_HOST    = os.environ.get('TARGET_HOST', 'fpga-sim')
TARGET_PORT    = int(os.environ.get('TARGET_PORT', '5000'))
REPLAY_RATE    = float(os.environ.get('REPLAY_RATE', '10.0'))   # 10x speed default
MAX_PACKETS    = int(os.environ.get('MAX_PACKETS', '0'))         # 0 = unlimited
LOOP           = os.environ.get('LOOP', 'false').lower() == 'true'
STARTUP_DELAY  = float(os.environ.get('STARTUP_DELAY', '10.0'))


# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    format='[ATTACK] %(message)s',
    level=logging.INFO,
)
log = logging.getLogger()


# ── Helpers ──────────────────────────────────────────────────
def extract_payload(pkt):
    """
    Pull the payload bytes from a packet.

    Strategy:
      - If TCP/UDP, use the Raw layer (the application-layer bytes)
      - If no Raw layer, just send the IP layer bytes (still tests CRC)
      - Skip pure-control packets (TCP SYN with no payload, etc.)
    """
    if Raw in pkt:
        return bytes(pkt[Raw].load)
    # Fall back to IP payload (header + data)
    if IP in pkt:
        return bytes(pkt[IP].payload)
    return None


def get_original_timing(reader):
    """First-pass: read timestamps to compute inter-packet delays."""
    return [pkt.time for pkt in reader]


# ── Main ─────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("  ATTACK PCAP REPLAYER")
    log.info("=" * 60)
    log.info(f"  PCAP file:      {ATTACK_PCAP}")
    log.info(f"  Target:         {TARGET_HOST}:{TARGET_PORT}")
    log.info(f"  Replay rate:    {REPLAY_RATE}x")
    log.info(f"  Max packets:    {MAX_PACKETS if MAX_PACKETS else 'unlimited'}")
    log.info(f"  Loop on EOF:    {LOOP}")
    log.info(f"  Startup delay:  {STARTUP_DELAY}s")
    log.info("=" * 60)

    # Verify file exists
    if not os.path.exists(ATTACK_PCAP):
        log.error(f"PCAP file not found: {ATTACK_PCAP}")
        return

    # Give the rest of the stack time to start up
    log.info(f"Sleeping {STARTUP_DELAY}s before attack (let diode stabilize)...")
    time.sleep(STARTUP_DELAY)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    iteration = 0
    while True:
        iteration += 1
        log.info(f"=== Iteration {iteration}: starting replay ===")

        sent_count = 0
        skipped_count = 0
        bytes_sent = 0
        start_time = time.time()
        prev_pkt_time = None

        try:
            reader = PcapReader(ATTACK_PCAP)
            for pkt in reader:
                # Inter-packet timing
                pkt_time = float(pkt.time)
                if prev_pkt_time is not None:
                    delay = (pkt_time - prev_pkt_time) / REPLAY_RATE
                    if delay > 0:
                        time.sleep(min(delay, 0.5))   # cap any huge gaps at 500ms
                prev_pkt_time = pkt_time

                # Extract payload
                payload = extract_payload(pkt)
                if not payload:
                    skipped_count += 1
                    continue

                # Skip extremely small or control-only packets
                if len(payload) < 1:
                    skipped_count += 1
                    continue

                # Cap payload at 2KB (matches FPGA recv buffer)
                payload = payload[:2048]

                # Send to target
                try:
                    sock.sendto(payload, (TARGET_HOST, TARGET_PORT))
                    sent_count += 1
                    bytes_sent += len(payload)
                except Exception as e:
                    log.error(f"sendto failed: {e}")
                    time.sleep(0.5)
                    continue

                # Progress log every 1000 packets
                if sent_count % 1000 == 0:
                    elapsed = time.time() - start_time
                    rate = sent_count / elapsed if elapsed > 0 else 0
                    log.info(f"  sent={sent_count}  bytes={bytes_sent:,}  "
                             f"rate={rate:.0f}/s  skipped={skipped_count}")

                # Stop if cap reached
                if MAX_PACKETS and sent_count >= MAX_PACKETS:
                    log.info(f"Reached MAX_PACKETS={MAX_PACKETS}, stopping")
                    break

            elapsed = time.time() - start_time
            log.info(f"=== Iteration {iteration} done ===")
            log.info(f"  Total sent:    {sent_count} packets")
            log.info(f"  Total bytes:   {bytes_sent:,}")
            log.info(f"  Skipped:       {skipped_count}")
            log.info(f"  Elapsed:       {elapsed:.1f}s")
            log.info(f"  Avg rate:      {sent_count/elapsed:.0f} packets/sec")

        except Exception as e:
            log.error(f"Replay error: {e}")
            time.sleep(5)

        if not LOOP:
            log.info("Replay complete. Sleeping forever (container stays alive).")
            while True:
                time.sleep(60)

        log.info("Looping back to start of PCAP...")
        time.sleep(5)


if __name__ == '__main__':
    main()
