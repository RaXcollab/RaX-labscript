"""sys.path bootstrap so tests use the SHORT path that matches BLACS runtime.

Production code under userlib/user_devices/RemoteControl/ is imported by
BLACS as ``user_devices.RemoteControl.*`` (BLACS puts ``userlib/`` on
``sys.path``). Tests live under ``userlib/user_devices/RemoteControl/tests/``
and must use the SAME short path; importing via
``userlib.user_devices.RemoteControl.*`` would trip
``labscript_utils.double_import_denier`` once both paths get loaded in the
same process.

See [reference_double-import-denier-path-mismatch] in auto-memory.
"""
from __future__ import annotations

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_USERLIB_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "..", ".."))
if _USERLIB_DIR not in sys.path:
    sys.path.insert(0, _USERLIB_DIR)
