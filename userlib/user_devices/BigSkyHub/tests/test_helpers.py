"""Buffered-path gate must skip (not abort the shot) lasers the GUI reports
as unlaunched, offline, or interlock-rejected — keyed on the TYPED reply
fields (status / error.code), never on message prose. The messages below
deliberately OMIT the retired substrings so a regression back to
message-sniffing fails loudly.

Retired-substring -> typed-carrier mapping, pinned from
HugeSkyController.pyw's PROGRAM_VALUE handler:

  "unknown connection" -> status=UNKNOWN_CONNECTION, code=unknown_connection
  "laser disconnected" -> status=ERROR, code=laser_disconnected
                          (LOAD-BEARING: status alone does not skip)
  "rejected:"          -> status=REJECTED, code=<mixin code> |
                          rejected_unknown | rejected_did_not_take_effect
                          (the GUI translates every "rejected:" ERROR into a
                          typed REJECTED before it reaches BLACS)
"""
import logging

import pytest

from user_devices.BigSkyHub.blacs_workers import (
    BigSkyWorker,
    _laser_unavailable,
    should_skip_buffered_response,
)


def _bare():
    w = BigSkyWorker.__new__(BigSkyWorker)
    w.logger = logging.getLogger("test_bigsky_buffered")
    return w


def test_skips_typed_unknown_connection():
    skip, why = should_skip_buffered_response(
        {"status": "UNKNOWN_CONNECTION",
         "error": {"code": "unknown_connection",
                   "message": "ch YAG_2_power not launched", "retryable": False}})
    assert skip and "not launched" in why


def test_skips_typed_laser_disconnected():
    """LOAD-BEARING: an offline laser arrives as status=ERROR, so only
    error.code makes it tolerable."""
    skip, why = should_skip_buffered_response(
        {"status": "ERROR",
         "error": {"code": "laser_disconnected",
                   "message": "offline", "retryable": True}})
    assert skip and why == "offline"


@pytest.mark.parametrize("code", ["lamps_not_active",          # mixin (item 2B)
                                  "rejected_unknown",          # REJECTED default
                                  "rejected_did_not_take_effect"])  # GUI safety net
def test_skips_typed_rejected(code):
    skip, _ = should_skip_buffered_response(
        {"status": "REJECTED",
         "error": {"code": code, "message": "GUI refused", "retryable": False}})
    assert skip, code


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
    """Unmapped codes must behave exactly as before: fall through the gate
    AND raise via _check_response (the pairing transition_to_buffered uses),
    i.e. fail the shot."""
    assert should_skip_buffered_response(reply)[0] is False
    with pytest.raises(Exception):
        _bare()._check_response(reply, "buffered_program(YAG_1_voltage=725)")


def test_does_not_skip_success_or_none():
    assert should_skip_buffered_response({"status": "SUCCESS"})[0] is False
    assert should_skip_buffered_response(None)[0] is False


def test_send_cmd_attaches_typed_reply_to_the_exception():
    """_arm_laser's log-level gate reads exc.response — the base
    _check_response only bakes the code into the message string."""
    reply = {"status": "ERROR",
             "error": {"code": "laser_disconnected", "message": "offline",
                       "retryable": True}}
    w = _bare()
    w.remote_comms = type("C", (), {
        "program_value": staticmethod(lambda c, v, wait_for_lock=False: reply)})()
    with pytest.raises(Exception) as excinfo:
        w._send_cmd("YAG_1_lamps", 1.0, "arm: lamps=1")
    assert _laser_unavailable(getattr(excinfo.value, "response", None))
