"""Rehearsal step, run inside the engine image: a raw object that exists is not replaced.

Writes one object, writes the same name again, and reads the day back through the real storage client.
Exit 0 only when the second write raised and the first body is the one kept.
"""

import os
import sys
from datetime import datetime

from engine import raw_store
from engine.parsers import KST

raw_dir = os.environ["RAW_DIR"]
stamp = datetime(2026, 1, 1, 9, 0, tzinfo=KST)
print("first", raw_store.write(stamp, "ONCE", {"written": 1}, raw_dir))
try:
    raw_store.write(stamp, "ONCE", {"written": 2}, raw_dir)
except Exception as exc:  # the class name is the evidence; any accepted second write is the failure
    print("second", type(exc).__name__)
else:
    print("second write was accepted")
    sys.exit(1)
kept = raw_store.read_day(raw_dir, stamp.date())
print("kept", kept)
sys.exit(0 if kept == [("ONCE", {"written": 1})] else 1)
