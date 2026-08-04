"""Base worker typed-status policy: WRITES raise, READS skip.

SDK-free: build the worker via __new__ (skip blacs Worker.__init__) and
exercise only the pure-python methods. See
memory/feedback_remotecontrol-base-is-the-contract.
"""
import logging
import types
import pytest

from user_devices.RemoteControl.blacs_workers import RemoteControlWorker


def _bare_worker(replies):
    w = RemoteControlWorker.__new__(RemoteControlWorker)
    w.logger = logging.getLogger("test_worker_typed_status")
    w.remote_comms = types.SimpleNamespace(
        connected=True, check_remote_value=lambda c: replies[c])
    return w


# --- WRITE contract: _check_response must raise on every non-SUCCESS ---

@pytest.mark.parametrize("status", ["ERROR", "REJECTED", "TIMEOUT", "UNKNOWN_CONNECTION"])
def test_check_response_raises_on_non_success(status):
    w = RemoteControlWorker.__new__(RemoteControlWorker)
    with pytest.raises(Exception):
        w._check_response({"status": status,
                           "error": {"code": "x", "message": "m", "retryable": False}},
                          "write")


def test_check_response_raises_on_timeout_none():
    w = RemoteControlWorker.__new__(RemoteControlWorker)
    with pytest.raises(Exception):
        w._check_response(None, "write")


def test_check_response_passes_on_success():
    w = RemoteControlWorker.__new__(RemoteControlWorker)
    assert w._check_response({"status": "SUCCESS", "value": 1.0}, "write") is None


# --- READ contract: check paths skip non-SUCCESS, keep the healthy ones ---

def test_check_remote_values_skips_unknown_connection():
    w = _bare_worker({
        "4": {"status": "UNKNOWN_CONNECTION",
              "error": {"code": "setpoint_not_initialized", "message": "no setpoint",
                        "retryable": True}},
        "6": {"status": "SUCCESS", "value": 348.686},
    })
    w.child_output_connections = ["4", "6"]
    out = w.check_remote_values()          # must NOT raise
    assert out == {"6": 348.686}           # unset ch4 skipped, ch6 kept


def test_check_all_remote_values_skips_and_continues():
    w = _bare_worker({
        "4": {"status": "UNKNOWN_CONNECTION", "message": "no setpoint"},
        "6": {"status": "SUCCESS", "value": 348.686},
    })
    w.child_connections = ["4", "6"]
    out = w.check_all_remote_values()
    assert out == {"6": 348.686}


def test_check_remote_values_skips_success_with_no_value():
    # v2 encode_reply omits "value" when it is None (rastering CHECK_VALUE
    # before the first position read). Must skip, not KeyError (2026-07-30).
    w = _bare_worker({
        "x": {"status": "SUCCESS"},
        "y": {"status": "SUCCESS", "value": 1.5},
    })
    w.child_output_connections = ["x", "y"]
    assert w.check_remote_values() == {"y": 1.5}


def test_check_status_skips_success_with_no_value():
    w = _bare_worker({
        "x": {"status": "SUCCESS"},
        "y": {"status": "SUCCESS", "value": 2.0},
    })
    w.child_monitor_connections = ["x", "y"]
    assert w.check_status() == {"y": 2.0}


# --- program_manual error hook: base default is strict (raise) ---

def test_program_manual_default_hook_raises_and_stops_loop():
    """The base _on_program_manual_error re-raises: a refused front-panel
    write red-errors the tab (LaserLockDevice behavior) and later channels
    are not sent. Tolerant devices (Rastering, BigSky) override the hook."""
    calls = []

    def program_value(connection, value, wait_for_lock=False):
        calls.append(connection)
        return {"status": "ERROR",
                "error": {"code": "boom", "message": "no", "retryable": False}}

    w = RemoteControlWorker.__new__(RemoteControlWorker)
    w.logger = logging.getLogger("test_worker_typed_status")
    w.remote_comms = types.SimpleNamespace(
        connected=True, program_value=program_value)
    w._initial_fetch_done = True
    w.child_output_connections = ["a", "b"]
    with pytest.raises(Exception):
        w.program_manual({"a": 1.0, "b": 2.0})
    assert calls == ["a"]   # loop stopped at the first refusal
