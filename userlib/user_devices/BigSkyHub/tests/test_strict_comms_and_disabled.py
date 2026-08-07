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


def _empty_shot_h5(tmp_path):
    """Shot h5 with no remote_device_operation — the early-return T2B path."""
    import h5py

    path = str(tmp_path / "no_ops.h5")
    with h5py.File(path, "w") as f:
        f.create_group("devices").create_group(_DEVICE)
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
    reads = []
    w = _worker({"YAG_1_power": {"status": "ERROR",
                                 "error": {"code": "command_error",
                                           "message": "boom"}},
                 "YAG_2_power": {"status": "SUCCESS", "value": 12.5}},
                disabled=["YAG_1"], reads=reads)
    w.child_connections = ["YAG_1_power", "YAG_2_power"]
    assert w.check_all_remote_values() == {"YAG_2_power": 12.5}
    # The disabled laser must not be polled at all — the returned dict alone
    # can't tell a skip from a dropped non-SUCCESS read.
    assert reads == ["YAG_2_power"]


def test_check_remote_values_skips_disabled():
    reads = []
    w = _worker({"YAG_1_voltage": _DISCONNECTED,
                 "YAG_2_voltage": {"status": "SUCCESS", "value": 725.0}},
                disabled=["YAG_1"], reads=reads)
    w.child_output_connections = ["YAG_1_voltage", "YAG_2_voltage"]
    assert w.check_remote_values() == {"YAG_2_voltage": 725.0}
    assert reads == ["YAG_2_voltage"]


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


# R5 at the shot level. The unit tests above only prove _arm_laser /
# _verify_armed_state raise; these prove the raise reaches the queue from BOTH
# _auto_arm_if_needed call sites in transition_to_buffered — the normal path
# (blacs_workers.py:413) and the "h5 has no remote_device_operation" path
# (:362). master wrapped the arm in a blanket try/except, so re-adding one
# would silently restore the old swallow with every unit test still green.

def _keep_warm_worker():
    """Enabled keep-warm YAG_1 that is offline; YAG_2 programs fine."""
    w = _worker({"YAG_2_voltage": _SUCCESS, "YAG_1_lamp_mode": _DISCONNECTED})
    w._keep_warm = {"YAG_1": True}
    return w


def test_buffered_propagates_arm_failure_with_programmed_channels(tmp_path):
    with pytest.raises(Exception, match="laser_disconnected"):
        _keep_warm_worker().transition_to_buffered(
            _DEVICE, _shot_h5(tmp_path, {"YAG_2_voltage": 725.0}), {}, True)


def test_buffered_propagates_arm_failure_without_remote_device_operation(tmp_path):
    with pytest.raises(Exception, match="laser_disconnected"):
        _keep_warm_worker().transition_to_buffered(
            _DEVICE, _empty_shot_h5(tmp_path), {}, True)


def test_update_disabled_round_trip():
    w = _worker({})
    w.update_disabled("YAG_1", True)
    w.update_disabled("YAG_1", False)
    assert w._disabled == set()


# ── init() seeding ───────────────────────────────────────────────────
# The only path that carries a saved "Disabled" tick across a BLACS or tab
# restart: tab get_save_data -> restore_save_data -> initialise_workers
# kwarg 'disabled_state' -> BigSkyWorker.init(). A kwarg-name drift on either
# side silently re-enables every laser.

def _init_worker(**kwargs):
    w = BigSkyWorker.__new__(BigSkyWorker)
    w.logger = logging.getLogger("test_bigsky_strict")
    w.mock = True                     # keeps RemoteCommunication socket-free
    w.host = None
    w.port = None
    w.child_output_connections = []
    w.child_monitor_connections = []
    w.device_name = _DEVICE
    for name, value in kwargs.items():
        setattr(w, name, value)
    w.init()
    return w


def test_init_seeds_disabled_from_tab_kwarg():
    w = _init_worker(disabled_state={"YAG_1": True, "YAG_2": False})
    assert w._disabled == {"YAG_1"}


def test_init_defaults_to_all_enabled_without_kwarg():
    assert _init_worker()._disabled == set()


# ── tab restore_save_data -> worker sync ─────────────────────────────
# restore_save_data runs twice: at tab init (no worker yet — the create_worker
# kwarg seeds it) and at RUNTIME from DeviceTab.update_from_settings via
# File > Load front panel. Skipping the runtime sync leaves the checkbox
# reading ENABLED while the worker keeps skipping that YAG's shot channels.

class _FakeCheckBox:
    def __init__(self):
        self.checked = None

    def blockSignals(self, _):
        pass

    def setChecked(self, state):
        self.checked = state


def _tab(primary_worker):
    from user_devices.BigSkyHub.blacs_tabs import BigSkyTab

    t = BigSkyTab.__new__(BigSkyTab)
    t._primary_worker = primary_worker
    t._keep_warm, t._keep_warm_temp, t._disabled = {}, {}, {}
    t._warmup_triggered = {}
    t._keep_warm_buttons = {"YAG_1": _FakeCheckBox()}
    t._keep_warm_temp_buttons = {"YAG_1": _FakeCheckBox()}
    t._disabled_buttons = {"YAG_1": _FakeCheckBox(), "YAG_2": _FakeCheckBox()}
    t._update_keep_warm_interlocks = lambda prefix: None
    t._apply_disabled_ui = lambda prefix: None
    t.synced = []
    t._sync_disabled_to_worker = lambda p, s: t.synced.append(("disabled", p, s))
    t._sync_keep_warm_to_worker = lambda p, s: t.synced.append(("keep_warm", p, s))
    return t


def test_restore_save_data_syncs_live_worker():
    t = _tab("main_worker")
    t.restore_save_data({"disabled": {"YAG_1": True, "YAG_2": False},
                         "keep_warm": {"YAG_1": True}})
    assert t._disabled == {"YAG_1": True, "YAG_2": False}
    assert t.synced == [("keep_warm", "YAG_1", True),
                        ("disabled", "YAG_1", True),
                        ("disabled", "YAG_2", False)]


def test_restore_save_data_skips_sync_before_worker_exists():
    t = _tab(None)                    # DeviceTab.__init__ ordering
    t.restore_save_data({"disabled": {"YAG_1": True}, "keep_warm": {"YAG_1": True}})
    assert t._disabled == {"YAG_1": True} and t.synced == []


def test_get_save_data_includes_disabled():
    # Without this key a Disabled tick silently stops surviving a restart
    # (degrades loud -- the laser comes back ENABLED -- but still a trap).
    t = _tab("main_worker")
    t._disabled = {"YAG_1": True, "YAG_2": False}
    assert t.get_save_data()["disabled"] == {"YAG_1": True, "YAG_2": False}


def test_restore_warmup_skips_disabled_laser():
    # Uniformity guard: every worker path must respect Disabled, including the
    # keep-warm restore (tab-side auto path is guarded too; this is the choke point).
    w = _init_worker(disabled_state={"YAG_1": True})
    # Mock init leaves connected=False, whose own early-return would mask a
    # deleted guard -- force True so only the Disabled guard can skip.
    w.remote_comms.connected = True
    w._is_armed = {"YAG_1": True}
    w._last_sent_values = {}
    sent = []
    w._send_cmd = lambda conn, value, ctx: sent.append(conn)
    w._restore_warmup("YAG_1")
    assert sent == [] and w._is_armed == {"YAG_1": True}
