# ══════════════════════════════════════════════════════════════
#  load.zeek — Module 4 Zeek loader
#
#  Usage:
#    cd /lab/work
#    zeek -C -r /lab/pcaps/attack.pcapng /lab/zeek/load.zeek
#
#  Produces in cwd:
#    conn.log              — TCP connections (always)
#    modbus.log            — stock Zeek Modbus connection log
#    modbus_detailed.log   — icsnpp register-level log (addr + values)
#
#  -C disables checksum validation (Docker bridge captures have
#  wrong TCP checksums because of NIC hardware-offload semantics;
#  without -C Zeek silently drops every Modbus frame).
# ══════════════════════════════════════════════════════════════

# Stock Modbus analyzer
@load base/protocols/modbus

# CISA/INL register-level Modbus parser. Installed via zkg at
# container build time; provides modbus_detailed.log with
# per-frame register addresses, quantities, and values.
@load packages/icsnpp-modbus
