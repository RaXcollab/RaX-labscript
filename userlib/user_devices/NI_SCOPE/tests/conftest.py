"""sys.path bootstrap so tests use the SHORT path that matches BLACS runtime.

See sibling docstring in NuvuCamera/tests/conftest.py.
"""
from __future__ import annotations

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_USERLIB_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "..", ".."))
if _USERLIB_DIR not in sys.path:
    sys.path.insert(0, _USERLIB_DIR)
