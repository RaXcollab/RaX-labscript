"""N1-N3: canonical invariants for the SDK-free NuvuCamera helpers.

Tests pure-Python functions extracted to ``user_devices.NuvuCamera._helpers``
per T6.1 audit. No Nuvu SDK required.

Run:
    conda activate labscript && python -m pytest \
        userlib/user_devices/NuvuCamera/tests/ -v
"""
from __future__ import annotations

import pytest

from user_devices.NuvuCamera._helpers import apply_attribute_update


def test_N1_apply_attribute_update_mutates_dict_in_place():
    """The helper MUST mutate the passed dict and return ``(name, value)``."""
    attrs = {"exposure_time": 0.1, "em_gain": 5}
    out = apply_attribute_update(attrs, "exposure_time", 0.2)

    assert attrs["exposure_time"] == 0.2, "dict mutation did not happen"
    assert attrs["em_gain"] == 5, "unrelated key was clobbered"
    assert out == ("exposure_time", 0.2), "return value contract broken"


def test_N2_apply_attribute_update_creates_missing_key():
    """Setting a new attribute creates the key (matches dict[key] = value semantics)."""
    attrs = {}
    apply_attribute_update(attrs, "trigger_mode", "external")
    assert attrs == {"trigger_mode": "external"}


def test_N3_apply_attribute_update_overwrites_with_value_types():
    """The helper preserves the value type exactly (no coercion). Tests
    int, float, bool, str, None, list, dict to confirm no surprise
    re-encoding happens between the helper and the SDK boundary."""
    attrs = {}
    cases = [
        ("int_attr", 42),
        ("float_attr", 0.5),
        ("bool_attr", True),
        ("str_attr", "external"),
        ("none_attr", None),
        ("list_attr", [1, 2, 3]),
        ("dict_attr", {"nested": 1}),
    ]
    for name, value in cases:
        apply_attribute_update(attrs, name, value)
        assert attrs[name] == value
        assert type(attrs[name]) is type(value)
