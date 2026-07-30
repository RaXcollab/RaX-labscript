"""S1-S2: canonical invariants for the SDK-free NI_SCOPE helpers.

Tests pure-Python functions extracted to ``user_devices.NI_SCOPE._helpers``
per T6.1 audit. No niscope required.

Run:
    conda activate labscript && python -m pytest \
        userlib/user_devices/NI_SCOPE/tests/ -v
"""
from __future__ import annotations

import pytest

from user_devices.NI_SCOPE._helpers import normalize_trigger_source


@pytest.mark.parametrize("src,expected", [
    # immediate
    (None, (None, "immediate")),
    ("", (None, "immediate")),
    # analog: TRIG canonical + digit-only
    ("TRIG", ("TRIG", "analog")),
    ("0", ("0", "analog")),
    ("7", ("7", "analog")),
    # analog: aliased forms (case-insensitive match against upper-cased alias keys)
    ("EXTERNAL", ("TRIG", "analog")),
    ("external", ("TRIG", "analog")),
    ("/PXI1Slot2/TRIG", ("TRIG", "analog")),  # mixed case form (R3 fix: was the missing alias case)
    ("/pxi1slot2/trig", ("TRIG", "analog")),  # all-lowercase still matches via upper()
    # bytes input -> decoded -> analog
    (b"TRIG", ("TRIG", "analog")),
    (bytearray(b"EXTERNAL"), ("TRIG", "analog")),
    (b"/PXI1Slot2/TRIG", ("TRIG", "analog")),  # bytes form of the second alias
    # digital: PFI / PXI_TRIG / /PXI1Slot prefixes
    ("PFI0", ("PFI0", "digital")),
    ("pfi3", ("pfi3", "digital")),
    ("PXI_TRIG0", ("PXI_TRIG0", "digital")),
    ("/PXI1Slot3/PFI0", ("/PXI1Slot3/PFI0", "digital")),
    # fallback: anything else -> analog
    ("UnknownThing", ("UnknownThing", "analog")),
])
def test_S1_normalize_trigger_source_canonical_mappings(src, expected):
    """The canonical (src, mode) mapping is pinned. Bytes get UTF-8-decoded
    (errors='ignore'); aliases collapse to 'TRIG'; PFI/PXI_TRIG/PXI1Slot
    prefixes are digital; everything else is analog (fallback)."""
    assert normalize_trigger_source(src) == expected


def test_S2_normalize_trigger_source_strips_whitespace_and_handles_case():
    """Whitespace around the source is stripped; case is normalized for
    matching but the returned src preserves the (whitespace-stripped) form
    for the canonical-TRIG path."""
    assert normalize_trigger_source("  TRIG  ") == ("TRIG", "analog")
    assert normalize_trigger_source("  external ") == ("TRIG", "analog")
    # case preservation on fallback (anything not recognized as TRIG/alias)
    src, mode = normalize_trigger_source("PFI7")
    assert mode == "digital"
    assert "PFI" in src.upper()
