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
