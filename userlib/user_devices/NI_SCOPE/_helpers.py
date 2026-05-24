"""SDK-free pure-Python helpers for NI_SCOPE (extracted per T6.1 audit).

This module does NOT import ``niscope``, so it can be loaded and unit-tested
in any environment that has the userlib path on ``sys.path``. The hardware-
bound helpers (``_to_vertical_coupling_enum``, trigger configuration) stay
on ``NI_SCOPEWorker`` in ``blacs_workers.py`` because they reference
``niscope.VerticalCoupling`` / ``niscope.TriggerSlope`` / ``niscope.TriggerCoupling``
directly.

Test surface lives at ``userlib/user_devices/NI_SCOPE/tests/test_helpers.py``.
"""
from __future__ import annotations


def normalize_trigger_source(src):
    """Return ``(src_norm, mode)`` where ``mode`` is ``'analog'``, ``'digital'``,
    or ``'immediate'``.

    Pure-Python: only str/bytes manipulation, no SDK dependency.

    Inputs:
      ``None`` / ``""``                    → immediate (no source)
      ``bytes`` / ``bytearray``            → decoded UTF-8 (errors='ignore')
      ``"EXTERNAL"`` / ``"/PXI1Slot2/TRIG"`` → aliased to ``"TRIG"``, analog
      digit-only string / ``"TRIG"``       → analog
      starts with ``PFI`` / ``PXI_TRIG`` /
        ``/PXI1Slot``                      → digital
      anything else                        → analog (fallback)

    The print-side "[NI_SCOPE] Mapping ..." log line lives on the worker
    method that wraps this helper, not here, so call sites that import
    ``_helpers`` directly stay quiet.
    """
    if src in (None, ""):
        return None, "immediate"
    if isinstance(src, (bytes, bytearray)):
        src = src.decode("utf-8", errors="ignore")

    s = str(src).strip()
    key = s.upper()

    aliases = {
        "EXTERNAL": "TRIG",
        "/PXI1SLOT2/TRIG": "TRIG",
    }
    if key in aliases:
        s = aliases[key]
        key = s.upper()

    if s.isdigit() or key == "TRIG":
        return s, "analog"

    if (key.startswith("PFI")
            or key.startswith("PXI_TRIG")
            or key.startswith("/PXI1SLOT")):
        return s, "digital"

    return s, "analog"
