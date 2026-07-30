"""Gate must skip (not abort) lasers the GUI reports as unlaunched or
interlock-rejected, across BOTH v1-legacy (ERROR + message substring)
and v2-typed (UNKNOWN_CONNECTION / REJECTED) reply shapes."""
from user_devices.BigSkyHub.blacs_workers import should_skip_buffered_response


def test_skips_v2_unknown_connection():
    skip, why = should_skip_buffered_response(
        {"status": "UNKNOWN_CONNECTION",
         "error": {"code": "unknown_connection",
                   "message": "unknown connection YAG2_power", "retryable": False}})
    assert skip and "unknown connection" in why


def test_skips_v2_rejected():
    skip, why = should_skip_buffered_response(
        {"status": "REJECTED",
         "error": {"code": "interlock", "message": "rejected: flow interlock",
                   "retryable": False}})
    assert skip


def test_skips_legacy_error_substrings():
    for msg in ("unknown connection YAG2", "laser disconnected", "rejected: warmup"):
        skip, _ = should_skip_buffered_response({"status": "ERROR", "message": msg})
        assert skip, msg


def test_does_not_skip_success_or_none_or_other_errors():
    assert should_skip_buffered_response({"status": "SUCCESS"})[0] is False
    assert should_skip_buffered_response(None)[0] is False
    assert should_skip_buffered_response(
        {"status": "ERROR", "message": "serial write failed"})[0] is False
