"""Strict comms for ENABLED lasers, silent skip for DISABLED ones.

Write paths (transition_to_buffered, program_manual, _arm_laser,
_verify_armed_state) raise on ANY non-SUCCESS reply or transport timeout —
that is what fails the shot and pauses the queue. The escape hatch is the
per-laser Disabled checkbox: a disabled prefix is skipped before anything is
sent, and is omitted from the read polls. Reads still never raise.
"""
import logging
import types

import numpy as np
import pytest

from user_devices.BigSkyHub.blacs_workers import BigSkyWorker

_DEVICE = "BigSkyLasers"

_DISCONNECTED = {"status": "ERROR",
                 "error": {"code": "laser_disconnected", "message": "offline",
                           "retryable": True}}
_REJECTED = {"status": "REJECTED",
             "error": {"code": "lamps_not_active", "message": "GUI refused",
                       "retryable": False}}
_SUCCESS = {"status": "SUCCESS"}


def _shot_h5(tmp_path, columns):
    """Write a shot h5 with devices/<name>/remote_device_operation."""
    import h5py

    path = str(tmp_path / "shot.h5")
    table = np.array(
        [tuple(columns.values())],
        dtype=[(col, "f8") for col in columns],
    )
    with h5py.File(path, "w") as f:
        f.create_group("devices").create_group(_DEVICE).create_dataset(
            "remote_device_operation", data=table)
    return path


def _worker(replies, disabled=(), sends=None, reads=None):
    """Bare worker wired to a dict-driven fake transport.

    ``replies`` maps a connection name to its reply (or a callable). A missing
    key yields None — the transport-timeout case.
    """
    def _reply(conn):
        r = replies.get(conn)
        return r(conn) if callable(r) else r

    w = BigSkyWorker.__new__(BigSkyWorker)
    w.logger = logging.getLogger("test_bigsky_strict")
    w.enable_comms = True
    w.device_name = _DEVICE
    w._initial_fetch_done = True
    w._disabled = set(disabled)
    w._keep_warm = {}
    w._is_armed = {}
    w._last_sent_values = {}
    w.child_connections = []
    w.child_output_connections = []

    def program_value(conn, value, wait_for_lock=False):
        if sends is not None:
            sends.append(conn)
        return _reply(conn)

    def check_remote_value(conn):
        if reads is not None:
            reads.append(conn)
        return _reply(conn)

    w.remote_comms = types.SimpleNamespace(
        connected=True,
        program_value=program_value,
        check_remote_value=check_remote_value,
    )
    return w


# ── transition_to_buffered ───────────────────────────────────────────

def test_buffered_raises_on_laser_disconnected_when_enabled(tmp_path):
    w = _worker({"YAG_1_voltage": _DISCONNECTED})
    with pytest.raises(Exception):
        w.transition_to_buffered(
            _DEVICE, _shot_h5(tmp_path, {"YAG_1_voltage": 700.0}), {}, True)


def test_buffered_raises_on_rejected_when_enabled(tmp_path):
    w = _worker({"YAG_1_qswitch": _REJECTED})
    with pytest.raises(Exception):
        w.transition_to_buffered(
            _DEVICE, _shot_h5(tmp_path, {"YAG_1_qswitch": 1.0}), {}, True)


def test_buffered_raises_on_transport_none_when_enabled(tmp_path):
    w = _worker({})           # no reply registered -> transport returns None
    with pytest.raises(Exception):
        w.transition_to_buffered(
            _DEVICE, _shot_h5(tmp_path, {"YAG_1_voltage": 700.0}), {}, True)


def test_buffered_skips_disabled_laser_without_sending(tmp_path):
    sends = []
    w = _worker({"YAG_1_voltage": _DISCONNECTED, "YAG_2_voltage": _SUCCESS},
                disabled=["YAG_1"], sends=sends)
    w.transition_to_buffered(
        _DEVICE,
        _shot_h5(tmp_path, {"YAG_1_voltage": 700.0, "YAG_2_voltage": 725.0}),
        {}, True)
    assert sends == ["YAG_2_voltage"]


# ── program_manual ───────────────────────────────────────────────────

def test_program_manual_raises_on_laser_disconnected_when_enabled():
    w = _worker({"YAG_1_voltage": _DISCONNECTED})
    w.child_output_connections = ["YAG_1_voltage"]
    with pytest.raises(Exception):
        w.program_manual({"YAG_1_voltage": 700})


def test_program_manual_raises_on_transport_none_when_enabled():
    w = _worker({})
    w.child_output_connections = ["YAG_1_voltage"]
    with pytest.raises(Exception):
        w.program_manual({"YAG_1_voltage": 700})


def test_program_manual_sends_later_channels_after_success():
    w = _worker({"YAG_1_voltage": _SUCCESS, "YAG_2_voltage": _SUCCESS})
    w.child_output_connections = ["YAG_1_voltage", "YAG_2_voltage"]
    w.program_manual({"YAG_1_voltage": 700, "YAG_2_voltage": 725})
    assert w._last_sent_values == {"YAG_1_voltage": 700, "YAG_2_voltage": 725}


def test_program_manual_skips_disabled_laser_without_sending():
    sends = []
    w = _worker({"YAG_1_voltage": _DISCONNECTED, "YAG_2_voltage": _SUCCESS},
                disabled=["YAG_1"], sends=sends)
    w.child_output_connections = ["YAG_1_voltage", "YAG_2_voltage"]
    w.program_manual({"YAG_1_voltage": 700, "YAG_2_voltage": 725})
    assert sends == ["YAG_2_voltage"]


# ── reads ────────────────────────────────────────────────────────────

def test_check_all_remote_values_skips_disabled_and_never_raises():
    w = _worker({"YAG_1_power": {"status": "ERROR",
                                 "error": {"code": "command_error",
                                           "message": "boom"}},
                 "YAG_2_power": {"status": "SUCCESS", "value": 12.5}},
                disabled=["YAG_1"])
    w.child_connections = ["YAG_1_power", "YAG_2_power"]
    assert w.check_all_remote_values() == {"YAG_2_power": 12.5}


def test_check_remote_values_skips_disabled():
    w = _worker({"YAG_1_voltage": _DISCONNECTED,
                 "YAG_2_voltage": {"status": "SUCCESS", "value": 725.0}},
                disabled=["YAG_1"])
    w.child_output_connections = ["YAG_1_voltage", "YAG_2_voltage"]
    assert w.check_remote_values() == {"YAG_2_voltage": 725.0}


# ── arm path ─────────────────────────────────────────────────────────

def test_verify_armed_state_raises_on_transport_none():
    with pytest.raises(Exception):
        _worker({})._verify_armed_state("YAG_1")


def test_verify_armed_state_raises_on_laser_disconnected():
    with pytest.raises(Exception):
        _worker({"YAG_1_lamp_mode": _DISCONNECTED})._verify_armed_state("YAG_1")


def test_verify_armed_state_false_on_value_mismatch():
    w = _worker({"YAG_1_lamp_mode": {"status": "SUCCESS", "value": 1.0},
                 "YAG_1_lamps": {"status": "SUCCESS", "value": 0.0}})
    assert w._verify_armed_state("YAG_1") is False


def test_arm_laser_raises_on_laser_disconnected():
    with pytest.raises(Exception):
        _worker({"YAG_1_stop": _DISCONNECTED})._arm_laser("YAG_1")


def test_auto_arm_skips_disabled_keep_warm_laser():
    sends, reads = [], []
    w = _worker({}, disabled=["YAG_1"], sends=sends, reads=reads)
    w._keep_warm = {"YAG_1": True}
    w._auto_arm_if_needed()          # must not raise on the dead transport
    assert sends == [] and reads == []


def test_update_disabled_round_trip():
    w = _worker({})
    w.update_disabled("YAG_1", True)
    w.update_disabled("YAG_1", False)
    assert w._disabled == set()
