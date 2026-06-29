#!/usr/bin/env python3
"""
your_s7_client.py — STUDENT TASK §1.3

Write a snap7 client that:
  1. Connects to plc-s7 (rack=0, slot=1)
  2. Reads 30 bytes from DB1 starting at offset 0  → recon
  3. Writes the value 9999 to DB1.DBW0            → attack
        (big-endian uint16 = bytes  \\x27\\x0f)

Hint imports:
  import snap7, socket

snap7.client.Client() is your entry point. libsnap7 does NOT resolve
DNS, so you must use socket.gethostbyname() first.
"""

# TODO — write your code here. ~10 lines is enough.
