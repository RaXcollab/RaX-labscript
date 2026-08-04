"""BigSky program_manual tolerance is keyed on typed reply fields, not
message substrings: the old gates still worked (program_value aliases
error.message into the top-level message key) but message text is prose,
not a contract. Several messages below deliberately OMIT the legacy
substrings so a regression back to message-sniffing fails loudly.
Envelope shapes mirror HugeSkyController.pyw's PROGRAM_VALUE handler."""
import logging
import types

import pytest

from user_devices.BigSkyHub.blacs_workers import BigSkyWorker


def _bare():
    w = BigSkyWorker.__new__(BigSkyWorker)
    w.logger = logging.getLogger("test_bigsky_program_manual")
    return w


def _exc():
    return Exception("Server X (program_manual(...)): refused")


def test_unknown_connection_skipped():
    _bare()._on_program_manual_error("YAG_9_voltage", 725, {
        "status": "UNKNOWN_CONNECTION",
        "error": {"code": "unknown_connection",
                  "message": "ch YAG_9 not launched", "retryable": False},
    }, _exc())   # returns without raising


def test_laser_disconnected_skipped():
    _bare()._on_program_manual_error("YAG_1_voltage", 725, {
        "status": "ERROR",
        "error": {"code": "laser_disconnected",
                  "message": "offline", "retryable": True},
    }, _exc())


def test_rejected_skipped():
    _bare()._on_program_manual_error("YAG_1_qswitch", 1, {
        "status": "REJECTED",
        "error": {"code": "serial_failure",
                  "message": "rejected: serial failure", "retryable": False},
    }, _exc())


def test_command_error_raises():
    with pytest.raises(Exception):
        _bare()._on_program_manual_error("YAG_1_voltage", 725, {
            "status": "ERROR",
            "error": {"code": "command_error",
                      "message": "unknown error", "retryable": False},
        }, _exc())


def test_timeout_envelope_raises():
    with pytest.raises(Exception):
        _bare()._on_program_manual_error("YAG_1_voltage", 725, {
            "status": "TIMEOUT",
            "error": {"code": "command_timeout",
                      "message": "timeout waiting", "retryable": True},
        }, _exc())


def _loop_worker(replies):
    w = _bare()
    w.remote_comms = types.SimpleNamespace(
        connected=True,
        program_value=lambda c, v, wait_for_lock=False: replies[c])
    w._initial_fetch_done = True
    w._keep_warm = {}
    w._last_sent_values = {}
    w.child_output_connections = ["YAG_1_voltage", "YAG_2_voltage"]
    return w


def test_loop_skips_disconnected_laser_without_caching_value():
    """Loop invariant: a tolerated failure must NOT update _last_sent_values
    (so the next push retries once the laser is back), and later channels
    are still sent."""
    w = _loop_worker({
        "YAG_1_voltage": {"status": "ERROR",
                          "error": {"code": "laser_disconnected",
                                    "message": "offline", "retryable": True}},
        "YAG_2_voltage": {"status": "SUCCESS"},
    })
    w.program_manual({"YAG_1_voltage": 700, "YAG_2_voltage": 725})
    assert w._last_sent_values == {"YAG_2_voltage": 725}
