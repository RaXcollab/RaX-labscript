"""BigSky read overrides must skip typed non-SUCCESS (not depend on the
GUI's exact message substrings), via the shared base policy."""
import logging
import types

from user_devices.BigSkyHub.blacs_workers import BigSkyWorker


def _bare(replies):
    w = BigSkyWorker.__new__(BigSkyWorker)
    w.logger = logging.getLogger("test_bigsky_read")
    w._disabled = set()
    w.remote_comms = types.SimpleNamespace(
        connected=True, check_remote_value=lambda c: replies[c])
    return w


def test_check_all_skips_typed_unknown_without_substring():
    # Real BigSky names match _PREFIX_RE ^(.+?_\d+)_(.+)$; suffix "power" is NOT
    # in _COMMAND_SUFFIXES {'warmup','start_lasing','stop'}, so these are
    # readable channels (not command-skipped). The message has NO "unknown
    # connection" substring -> the old ladder would fall through and RAISE.
    w = _bare({
        "YAG_1_power": {"status": "UNKNOWN_CONNECTION",
                        "error": {"code": "unknown_connection",
                                  "message": "ch YAG_1_power not launched",
                                  "retryable": False}},
        "YAG_2_power": {"status": "SUCCESS", "value": 12.5},
    })
    w.child_connections = ["YAG_1_power", "YAG_2_power"]
    out = w.check_all_remote_values()      # must NOT raise
    assert out == {"YAG_2_power": 12.5}
