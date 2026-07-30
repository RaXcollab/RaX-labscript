"""sys.path bootstrap so tests use the SHORT path that matches BLACS runtime.

Production code under userlib/user_devices/BigSkyHub/ is imported by
BLACS as ``user_devices.BigSkyHub.*`` (BLACS puts ``userlib/`` on
``sys.path``). Tests live under ``userlib/user_devices/BigSkyHub/tests/``
and must use the SAME short path; importing via
``userlib.user_devices.BigSkyHub.*`` would trip
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
