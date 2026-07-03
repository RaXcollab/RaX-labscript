"""SDK-free pure-Python helpers for NuvuCamera (extracted per T6.1 audit).

These helpers do NOT import ``Nuvu_sdk``, so they can be loaded and unit-
tested in any environment that has the userlib path on ``sys.path``. The
hardware-bound counterparts live on ``NuvuCamera`` in ``blacs_workers.py``.

Test surface lives at ``userlib/user_devices/NuvuCamera/tests/test_helpers.py``.
"""
from __future__ import annotations


def apply_attribute_update(attrs, name, value):
    """Mutate ``attrs`` in place: ``attrs[name] = value``; return ``(name, value)``.

    Pure half of ``NuvuCamera.set_attribute``. The hardware-side
    ``camera_utils.set_attrs({name: value})`` call stays on the class because
    it dereferences the SDK handle.

    Returns the ``(name, value)`` pair so callers can chain or assert.
    """
    attrs[name] = value
    return (name, value)
