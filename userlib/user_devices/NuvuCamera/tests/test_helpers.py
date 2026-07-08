"""N1-N3: canonical invariants for the SDK-free NuvuCamera helpers.

Tests pure-Python functions extracted to ``user_devices.NuvuCamera._helpers``
per T6.1 audit. No Nuvu SDK required.

Run:
    conda activate labscript && python -m pytest \
        userlib/user_devices/NuvuCamera/tests/ -v
"""
from __future__ import annotations

import pytest

from user_devices.NuvuCamera._helpers import (
    CAMERA_OPEN_MAX_ATTEMPTS,
    CAMERA_OPEN_MAX_DELAY_S,
    SNAP_MAX_ATTEMPTS,
    apply_attribute_update,
    camera_open_failure_message,
    describe_error_code,
    open_retry_delays,
    should_resume_continuous,
    snap_should_retry,
    snap_timeout_message,
)


def test_N1_apply_attribute_update_mutates_dict_in_place():
    """The helper MUST mutate the passed dict and return ``(name, value)``."""
    attrs = {"exposure_time": 0.1, "em_gain": 5}
    out = apply_attribute_update(attrs, "exposure_time", 0.2)

    assert attrs["exposure_time"] == 0.2, "dict mutation did not happen"
    assert attrs["em_gain"] == 5, "unrelated key was clobbered"
    assert out == ("exposure_time", 0.2), "return value contract broken"


def test_N2_apply_attribute_update_creates_missing_key():
    """Setting a new attribute creates the key (matches dict[key] = value semantics)."""
    attrs = {}
    apply_attribute_update(attrs, "trigger_mode", "external")
    assert attrs == {"trigger_mode": "external"}


def test_N3_apply_attribute_update_overwrites_with_value_types():
    """The helper preserves the value type exactly (no coercion). Tests
    int, float, bool, str, None, list, dict to confirm no surprise
    re-encoding happens between the helper and the SDK boundary."""
    attrs = {}
    cases = [
        ("int_attr", 42),
        ("float_attr", 0.5),
        ("bool_attr", True),
        ("str_attr", "external"),
        ("none_attr", None),
        ("list_attr", [1, 2, 3]),
        ("dict_attr", {"nested": 1}),
    ]
    for name, value in cases:
        apply_attribute_update(attrs, name, value)
        assert attrs[name] == value
        assert type(attrs[name]) is type(value)


# ---------------------------------------------------------------------------
# TASK 1 — camera-open retry/backoff + error-code classification
# ---------------------------------------------------------------------------

def test_N4_open_retry_delays_default_is_bounded():
    """Default schedule has one sleep between each pair of attempts, is capped,
    and totals well under the ~15 s budget."""
    delays = open_retry_delays()
    assert len(delays) == CAMERA_OPEN_MAX_ATTEMPTS - 1
    assert all(d <= CAMERA_OPEN_MAX_DELAY_S for d in delays)
    assert sum(delays) < 15.0
    assert delays == [3.0, 5.0]


def test_N5_open_retry_delays_single_attempt_has_no_sleeps():
    assert open_retry_delays(max_attempts=1) == []


def test_N6_open_retry_delays_caps_backoff_growth():
    """Exponential growth is clamped at max_delay so a large attempt count can
    never blow the latency budget."""
    delays = open_retry_delays(max_attempts=4, base_delay=3.0, backoff=2.0, max_delay=5.0)
    # 3 -> 6(capped 5) -> 12(capped 5)
    assert delays == [3.0, 5.0, 5.0]


def test_N7_camera_open_failure_message_is_operator_facing():
    msg = camera_open_failure_message("Error 27: Could not find camera", max_attempts=3)
    assert "3 attempts" in msg
    assert "powered off" in msg
    assert "cable" in msg.lower()
    assert "restart button" in msg
    # includes the underlying error for diagnosis:
    assert "Error 27" in msg


def test_N8_describe_error_code_known_codes():
    assert "NC_ERROR_CAMERA_FOUND" in describe_error_code(27)
    assert "not supported" in describe_error_code(107)
    assert "did not arrive" in describe_error_code(214)
    # 101 is the closed-handle cascade fallout we are trying to avoid:
    assert "invalid" in describe_error_code(101).lower()


def test_N9_describe_error_code_unknown_points_at_header():
    out = describe_error_code(9999)
    assert "9999" in out
    assert "nc_error.h" in out


# ---------------------------------------------------------------------------
# TASK 2 — manual-snap retry decision
# ---------------------------------------------------------------------------

def test_N10_snap_should_retry_within_budget_then_stops():
    assert snap_should_retry(1) is True
    assert snap_should_retry(SNAP_MAX_ATTEMPTS - 1) is True
    assert snap_should_retry(SNAP_MAX_ATTEMPTS) is False
    assert snap_should_retry(SNAP_MAX_ATTEMPTS + 1) is False


def test_N11_snap_timeout_message_says_camera_still_open():
    msg = snap_timeout_message()
    assert "still open" in msg
    assert "214" in msg


# ---------------------------------------------------------------------------
# TASK 5 — idempotent continuous-view resume decision
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "continuous_dt, thread_running, expected",
    [
        (None, False, False),  # live view never started -> nothing to resume
        (None, True, False),   # (defensive) no interval retained
        (5.0, False, True),    # paused live view, not running -> resume
        (0, False, True),      # dt == 0 (max rate) is a valid resumable value
        (5.0, True, False),    # already running -> idempotent no-op
        (0, True, False),      # already running at max rate -> no double-start
    ],
)
def test_N12_should_resume_continuous_truth_table(continuous_dt, thread_running, expected):
    assert should_resume_continuous(continuous_dt, thread_running) is expected
