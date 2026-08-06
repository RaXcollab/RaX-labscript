"""Buffered-path replies that are NOT SUCCESS must fail the shot via
_check_response. The former typed-code tolerance (unlaunched / offline /
interlock-rejected lasers were skipped) is gone — a laser that should be
ignored is marked Disabled in the tab instead, which skips it before any
command is sent. See test_strict_comms_and_disabled.py.
"""
import logging

import pytest

from user_devices.BigSkyHub.blacs_workers import BigSkyWorker


def _bare():
    w = BigSkyWorker.__new__(BigSkyWorker)
    w.logger = logging.getLogger("test_bigsky_buffered")
    return w


@pytest.mark.parametrize("reply", [
    {"status": "ERROR", "error": {"code": "command_error",
                                  "message": "serial write failed"}},
    {"status": "ERROR", "error": {"code": "cannot_program_monitor",
                                  "message": "cannot program monitor"}},
    {"status": "ERROR", "error": {"code": "unknown_writable_param",
                                  "message": "unknown writable param"}},
    {"status": "TIMEOUT", "error": {"code": "command_timeout",
                                    "message": "timeout waiting"}},
    {"status": "ERROR", "error": {"code": "handler_exception",
                                  "message": "TypeError: boom"}},
])
def test_unmapped_code_not_skipped_and_raises(reply):
    """Unmapped codes raise via _check_response (the pairing
    transition_to_buffered uses), i.e. fail the shot."""
    with pytest.raises(Exception):
        _bare()._check_response(reply, "buffered_program(YAG_1_voltage=725)")
