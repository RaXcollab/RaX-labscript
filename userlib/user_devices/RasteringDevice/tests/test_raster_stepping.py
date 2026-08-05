"""Raster stepping: arm-once, step every Nth shot, finished/reset semantics.

SDK-free: build the worker via __new__ (skip blacs Worker.__init__) and
exercise _advance_raster / update_raster_mode / _init_raster_state directly
(transition_to_buffered's raster block delegates to _advance_raster; the
rest of it is h5 programming, untouched here).
"""
import logging

import numpy as np
import pytest

from user_devices.RasteringDevice.blacs_workers import (
    COMPOUND_XY, COORD_PAIR, RasteringWorker,
)

# After the worker import, never before: blacs_workers pulls in
# labscript_utils.h5_lock, which refuses to load once h5py is imported.
import h5py  # noqa: E402


SUCCESS = {"status": "SUCCESS"}
ARMED_STEP = {"status": "SUCCESS", "mode": "step"}
FINISHED = {"status": "SUCCESS", "finished": True}


class FakeComms:
    """Records program_value calls; replies from a per-connection dict."""

    def __init__(self, replies=None):
        self.connected = True
        self.calls = []  # list of (connection, value)
        self.replies = replies or {
            "arm_raster": ARMED_STEP, "move_to_next": SUCCESS}

    def program_value(self, connection, value, wait_for_lock=False):
        self.calls.append((connection, value))
        # Unstubbed connections succeed: tests opt in to failures.
        reply = self.replies.get(connection, SUCCESS)
        return reply(self) if callable(reply) else reply

    def connect_to_remote(self):
        return self.connected

    def sent(self, connection):
        return [c for c, _ in self.calls if c == connection]


def boom(comms):
    """A reply that blows up in transport instead of returning a status."""
    raise Exception("transport down")


STEPPED = {
    "status": "SUCCESS", "point_index": 3, "path_len": 10,
    "target_xy": [1.5, 2.5], "frame": "pixel",
    "calibration_matrix": [[2.0, 0.0], [0.0, 2.0]], "calibration_offset": [1.0, 2.0],
}


def make_worker(shots_per_step=1, replies=None, **workerargs):
    w = RasteringWorker.__new__(RasteringWorker)
    w.logger = logging.getLogger("test_raster_stepping")
    # Simulate workerargs landing as instance attributes, then the
    # production init path normalizing them.
    w.raster_mode = True
    w.shots_per_step = shots_per_step
    for key, val in workerargs.items():
        setattr(w, key, val)
    w._init_raster_state()
    w.remote_comms = FakeComms(replies)
    return w


# --- program_manual: courtesy writes never fail the tab (2026-08-04) ---

MOTOR_REFUSED = {"status": "ERROR", "error": {
    "code": "motor_move_failed",
    "message": "MoveTo(-0.0012) failed: Cannot move to requested position",
    "retryable": True}}


FPV = {"laser_raster_x_coord": 110.33, "laser_raster_y_coord": 63.2}


def _xy_worker(replies=None, outputs=COORD_PAIR):
    return make_worker(replies=replies, child_output_connections=list(outputs),
                       _initial_fetch_done=True)


def _spy_on_error_hook(w):
    """Record which connections reach the courtesy hook, then run the real
    policy (so a raise from it would still fail the test)."""
    seen = []
    policy = w._on_program_manual_error

    def spy(connection, value, response, exc):
        seen.append(connection)
        policy(connection, value, response, exc)

    w._on_program_manual_error = spy
    return seen


def test_program_manual_refused_pair_routes_through_hook_once():
    """A refused front-panel write (abort-path re-assert of an edge
    coordinate) warns and continues instead of raising to red-error the
    tab. The pair is ONE compound write, so it must reach the hook exactly
    once, labelled with the compound connection."""
    w = _xy_worker(replies={COMPOUND_XY: MOTOR_REFUSED})
    seen = _spy_on_error_hook(w)
    w.program_manual(dict(FPV))                        # must not raise
    assert seen == [COMPOUND_XY]


def test_program_manual_timeout_none_continues():
    """A transport timeout (None reply, e.g. dead GUI mid-abort) gets the
    same courtesy treatment: warn, keep going, remaining channel still
    sent. None reaches the hook -- there is no None pre-guard in the loop
    (unlike BigSky's)."""
    w = _xy_worker(replies={COMPOUND_XY: None},
                   outputs=list(COORD_PAIR) + ["future_knob"])
    seen = _spy_on_error_hook(w)
    w.program_manual({**FPV, "future_knob": 7.0})      # must not raise
    assert seen == [COMPOUND_XY]
    assert len(w.remote_comms.sent("future_knob")) == 1


# --- atomic (x, y): the pair is one compound write, never two axis writes ---

def test_program_manual_sends_one_compound_and_no_per_axis_write():
    w = _xy_worker()
    w.program_manual(dict(FPV))
    assert w.remote_comms.calls == [(COMPOUND_XY, [110.33, 63.2])]


def test_program_manual_single_coord_panel_keeps_single_axis_path():
    """A panel with only one coord programs that axis alone — the partner
    is never fabricated from a cached/echoed value."""
    w = _xy_worker(outputs=["laser_raster_x_coord"])
    w.program_manual({"laser_raster_x_coord": 110.33})
    assert w.remote_comms.calls == [("laser_raster_x_coord", 110.33)]


def _buffered_worker(tmp_path, columns, replies=None):
    """Worker + a shot file whose remote_device_operation carries `columns`
    ({connection: value}), wired for the setpoint path only."""
    w = _xy_worker(replies=replies)
    w.raster_mode = False                 # isolate setpoints from stepping
    w.enable_comms = True
    w.device_name = "RasteringGUI"
    w._pubsub_cache = {}
    table = np.zeros(1, dtype=[(c, np.float64) for c in columns])
    for connection, value in columns.items():
        table[connection] = value
    h5_path = tmp_path / "shot.h5"
    with h5py.File(h5_path, "w") as f:
        f.create_dataset(
            "devices/RasteringGUI/remote_device_operation", data=table)
    return w, str(h5_path)


def test_buffered_both_columns_send_one_compound(tmp_path):
    w, path = _buffered_worker(
        tmp_path, {"laser_raster_x_coord": 1.5, "laser_raster_y_coord": 2.5})
    w.transition_to_buffered("RasteringGUI", path, {}, True)
    assert w.remote_comms.calls == [(COMPOUND_XY, [1.5, 2.5])]


def test_buffered_single_column_keeps_single_axis_path(tmp_path):
    """A sequence that set only Raster_X emits one column. Filling the
    partner axis from front_panel_values would re-send a seconds-stale
    echo (the 2026-08-04 incident) — the GUI pairs a single-axis move with
    a fresh encoder read itself."""
    w, path = _buffered_worker(tmp_path, {"laser_raster_x_coord": 1.5})
    w.transition_to_buffered(
        "RasteringGUI", path, {"laser_raster_y_coord": 63.2}, True)
    assert w.remote_comms.calls == [("laser_raster_x_coord", 1.5)]


def test_buffered_compound_failure_raises(tmp_path):
    """Shot programming stays strict: a refused pair fails the shot."""
    w, path = _buffered_worker(
        tmp_path, {"laser_raster_x_coord": 1.5, "laser_raster_y_coord": 2.5},
        replies={COMPOUND_XY: MOTOR_REFUSED})
    with pytest.raises(Exception, match="motor_move_failed"):
        w.transition_to_buffered("RasteringGUI", path, {}, True)


# --- workerargs honored by init (the restart-desync fix) ---

def test_init_raster_state_honors_workerargs():
    w = make_worker(shots_per_step=5)
    assert w.raster_mode is True          # not clobbered back to False
    assert w.shots_per_step == 5


def test_init_raster_state_defaults_and_clamps():
    w = RasteringWorker.__new__(RasteringWorker)
    w._init_raster_state()                # no workerargs at all
    assert w.raster_mode is False and w.shots_per_step == 1
    w.shots_per_step = 0                  # bad value clamps to 1
    w._init_raster_state()
    assert w.shots_per_step == 1


# --- arm-once + step-every-Nth-shot ---

def test_arm_sent_once_before_first_step():
    w = make_worker()
    for _ in range(3):
        w._advance_raster()
    assert w.remote_comms.calls[0] == ("arm_raster", 0)
    assert w.remote_comms.calls[-1][0] == "move_to_next"   # arm precedes step
    assert len(w.remote_comms.sent("arm_raster")) == 1


def test_n3_steps_on_shots_1_and_4_only():
    w = make_worker(shots_per_step=3)
    step_counts = []
    for _ in range(6):
        w._advance_raster()
        step_counts.append(len(w.remote_comms.sent("move_to_next")))
    # move_to_next fires before shots 1 and 4 only
    assert step_counts == [1, 1, 1, 2, 2, 2]


# --- finished=True re-arms and wraps to the start of the path (no error) ---

def test_finished_rearms_and_wraps_to_path_start():
    # The wrapped step's reply must be distinguishable from the pre-wrap
    # step's, or the meta assertion is blind to stale _raster_meta.
    wrapped = dict(STEPPED, point_index=0)
    replies = {"arm_raster": ARMED_STEP,
               "move_to_next": lambda c: (
                   STEPPED if len(c.sent("move_to_next")) == 1 else
                   FINISHED if len(c.sent("move_to_next")) == 2 else wrapped)}
    w = make_worker(shots_per_step=3, replies=replies)
    for _ in range(3):
        w._advance_raster()               # arm + step, then 2 non-step shots
    w._advance_raster()                   # path exhausted -> re-arm + wrap, no raise
    assert len(w.remote_comms.sent("arm_raster")) == 2
    assert len(w.remote_comms.sent("move_to_next")) == 3
    assert w._raster_armed is True and w._shots_since_step == 1
    assert w._raster_meta["point_index"] == 0   # fresh meta from the wrapped step


def test_second_consecutive_finished_raises_instead_of_looping():
    # Production-unreachable (an empty path fails the re-ARM with
    # no_raster_configured before any move) — this pins the loop bound:
    # a GUI that keeps answering `finished` must fail the shot, not spin.
    replies = {"arm_raster": ARMED_STEP, "move_to_next": FINISHED}
    w = make_worker(replies=replies)
    with pytest.raises(Exception, match="empty"):
        w._advance_raster()
    assert w._raster_armed is False and w._shots_since_step == 0
    assert len(w.remote_comms.sent("arm_raster")) == 2   # re-arm was attempted once


def test_rearm_rejected_at_wrap_fails_shot_and_stays_unarmed():
    rejected = {"status": "REJECTED",
                "error": {"code": "no_raster_configured", "message": "m",
                          "retryable": False}}
    replies = {"arm_raster": lambda c: (
                   rejected if len(c.sent("arm_raster")) == 2 else ARMED_STEP),
               "move_to_next": lambda c: (
                   FINISHED if len(c.sent("move_to_next")) == 2 else STEPPED)}
    w = make_worker(replies=replies)
    w._advance_raster()                   # arm + normal step
    with pytest.raises(Exception, match="no_raster_configured"):
        w._advance_raster()               # wrap: re-arm rejected -> shot fails
    # Clean state for the requeued shot: it re-arms from scratch.
    assert w._raster_armed is False and w._shots_since_step == 0


# --- update_raster_mode resets the group count but keeps the raster armed ---

def test_update_raster_mode_resets_counter_but_does_not_rearm():
    w = make_worker(shots_per_step=3)
    w._advance_raster()                   # armed, counter at 1
    w.update_raster_mode(raster_mode=True, shots_per_step=2)
    assert w._shots_since_step == 0 and w.shots_per_step == 2
    # Re-arming restarts the path from point 1, so an N change on a live
    # raster must NOT re-arm — it only re-teaches N.
    assert w._raster_armed is True
    assert len(w.remote_comms.sent("arm_raster")) == 1
    w._advance_raster()                   # steps immediately, no second arm
    assert len(w.remote_comms.sent("arm_raster")) == 1
    assert len(w.remote_comms.sent("move_to_next")) == 2


# --- failed step does not advance the counter (retry re-steps) ---

def test_failed_step_leaves_counter_so_retry_resteps():
    rejected = {"status": "REJECTED",
                "error": {"code": "raster_step_failed", "message": "m",
                          "retryable": False}}
    replies = {"arm_raster": ARMED_STEP, "move_to_next": rejected}
    w = make_worker(shots_per_step=3, replies=replies)
    with pytest.raises(Exception):
        w._advance_raster()
    assert w._shots_since_step == 0       # counter NOT advanced
    w.remote_comms.replies["move_to_next"] = SUCCESS
    w._advance_raster()                   # retried shot steps again
    assert len(w.remote_comms.sent("move_to_next")) == 2


# --- failed arm never steps, stays unarmed ---

def test_failed_arm_does_not_step_and_stays_unarmed():
    rejected = {"status": "REJECTED",
                "error": {"code": "not_calibrated", "message": "m",
                          "retryable": False}}
    replies = {"arm_raster": rejected, "move_to_next": SUCCESS}
    w = make_worker(replies=replies)
    with pytest.raises(Exception):
        w._advance_raster()
    assert w._raster_armed is False
    assert w.remote_comms.sent("move_to_next") == []


# --- stale armed flag auto-heals on raster_not_active (GUI restart) ---

def test_raster_not_active_clears_armed_flag_so_next_call_rearms():
    not_active = {"status": "ERROR",
                  "error": {"code": "raster_not_active",
                            "message": "raster not active", "retryable": False}}
    w = make_worker()
    w._advance_raster()                   # armed against the live GUI
    w.remote_comms.replies["move_to_next"] = not_active
    with pytest.raises(Exception):
        w._advance_raster()
    assert w._raster_armed is False        # GUI restarted -> re-arm next time
    w.remote_comms.replies["move_to_next"] = SUCCESS
    w._advance_raster()
    assert len(w.remote_comms.sent("arm_raster")) == 2


def test_disconnected_raises():
    w = make_worker()
    w.remote_comms.connected = False
    with pytest.raises(Exception, match="not connected"):
        w._advance_raster()


# --- eager sync: the checkbox reaches the GUI now, not at the first shot ---

def test_toggle_on_arms_and_pushes_n_immediately():
    w = make_worker(shots_per_step=4, raster_mode=False)
    w.update_raster_mode(raster_mode=True, shots_per_step=4)
    assert w.remote_comms.calls == [("arm_raster", 0), ("shots_per_step", 4)]
    assert w._raster_armed is True


@pytest.mark.parametrize("arm_reply", [
    boom,                                  # transport blew up
    {"status": "REJECTED",                 # typed failure from the server
     "error": {"code": "not_calibrated", "message": "m", "retryable": False}},
], ids=["transport", "rejected"])
def test_toggle_on_failure_warns_and_never_raises(arm_reply):
    w = make_worker(raster_mode=False, replies={"arm_raster": arm_reply})
    w.update_raster_mode(raster_mode=True, shots_per_step=1)   # must not raise
    assert w._raster_armed is False        # lazy arm stays the backstop
    assert w.remote_comms.sent("shots_per_step") == []


def test_toggle_off_disarms_and_resets():
    w = make_worker(shots_per_step=3)
    w._advance_raster()                   # armed, counter at 1
    w.update_raster_mode(raster_mode=False, shots_per_step=3)
    assert w.remote_comms.sent("disarm_raster") == ["disarm_raster"]
    assert w._raster_armed is False and w._shots_since_step == 0
    assert w._last_synced_shots_per_step is None


def test_toggle_off_failure_never_raises_and_still_resets():
    # raster_in_continuous_mode: the GUI operator owns that raster.
    busy = {"status": "REJECTED",
            "error": {"code": "raster_in_continuous_mode", "message": "m",
                      "retryable": False}}
    w = make_worker(replies={"disarm_raster": busy})
    w._advance_raster()
    w.update_raster_mode(raster_mode=False, shots_per_step=1)   # must not raise
    assert w._raster_armed is False


def test_n_change_while_unchecked_sends_nothing():
    w = make_worker(raster_mode=False)
    w.update_raster_mode(raster_mode=False, shots_per_step=7)
    assert w.remote_comms.calls == []
    assert w.shots_per_step == 7


def test_n_change_while_armed_sends_only_n():
    w = make_worker()
    w._advance_raster()                   # arm + shots_per_step(1) + move
    w.remote_comms.calls.clear()
    w.update_raster_mode(raster_mode=True, shots_per_step=5)
    assert w.remote_comms.calls == [("shots_per_step", 5)]


def test_redundant_n_resend_is_skipped():
    w = make_worker(shots_per_step=2)
    w._advance_raster()
    w.remote_comms.calls.clear()
    w.update_raster_mode(raster_mode=True, shots_per_step=2)   # same N
    assert w.remote_comms.calls == []


def test_sync_while_disconnected_sends_nothing_and_never_raises():
    w = make_worker(raster_mode=False)
    w.remote_comms.connected = False
    w.update_raster_mode(raster_mode=True, shots_per_step=3)   # must not raise
    assert w.remote_comms.calls == []
    assert w._raster_armed is False


def test_reconnect_resyncs_from_scratch():
    w = make_worker(shots_per_step=3)
    w._advance_raster()                   # armed against the pre-restart GUI
    w.remote_comms.calls.clear()
    w._raster_armed = True                # stale belief; the GUI restarted
    assert w.connect_to_remote() is True
    assert w.remote_comms.calls == [("arm_raster", 0), ("shots_per_step", 3)]


# --- lazy arm re-teaches N, and failing to do so never fails the shot ---

def test_lazy_arm_also_sends_n():
    w = make_worker(shots_per_step=3)
    w._advance_raster()
    assert w.remote_comms.calls == [
        ("arm_raster", 0), ("shots_per_step", 3), ("move_to_next", 1)]


def test_lazy_arm_n_failure_does_not_fail_the_shot():
    w = make_worker(shots_per_step=3, replies={"shots_per_step": boom})
    w._advance_raster()                   # must not raise
    assert w._raster_armed is True
    assert len(w.remote_comms.sent("move_to_next")) == 1


# --- raster provenance stashed from the step reply, held across the group ---

def test_advance_raster_stashes_point_meta_and_holds_it_across_the_group():
    """transition_to_buffered stamps _raster_meta onto every shot, so it must
    survive the non-stepping shots of a group and carry no envelope fields."""
    w = make_worker(shots_per_step=2, replies={"move_to_next": STEPPED})
    w._advance_raster()
    assert w._raster_meta == {k: STEPPED[k] for k in (
        "point_index", "path_len", "target_xy", "frame",
        "calibration_matrix", "calibration_offset")}
    assert "status" not in w._raster_meta

    w._advance_raster()                   # second shot of the group: no step
    assert len(w.remote_comms.sent("move_to_next")) == 1
    assert w._raster_meta["point_index"] == 3


# --- /data belongs to the queue manager until the shot is over ---

def _shot_worker(tmp_path, shot_name="shot.h5"):
    """Worker + an empty shot file, wired for the h5-writing lifecycle calls."""
    w = make_worker(replies={"move_to_next": STEPPED})
    w.enable_comms = True
    w.device_name = "RasteringGUI"
    w._pubsub_cache = {}
    w.initial_monitor_values = {}         # base post_experiment: nothing to save
    h5_path = tmp_path / shot_name
    with h5py.File(h5_path, "w") as f:
        f.create_group("devices/RasteringGUI")
    w.h5_filepath = str(h5_path)
    return w, h5_path


def test_transition_to_buffered_leaves_data_group_to_blacs(tmp_path):
    """Creating /data before the shot ends aborts the shot at
    experiment_queue.py:910 (ValueError: name already exists)."""
    w, h5_path = _shot_worker(tmp_path)
    w.transition_to_buffered("RasteringGUI", str(h5_path), {}, True)
    with h5py.File(h5_path, "r") as f:
        assert "data" not in f["/"]


def test_post_experiment_stamps_the_point_after_blacs_makes_data(tmp_path):
    w, h5_path = _shot_worker(tmp_path)
    w.transition_to_buffered("RasteringGUI", str(h5_path), {}, True)
    with h5py.File(h5_path, "r+") as f:   # stand in for experiment_queue.py:910
        f["/"].require_group("data")

    w.post_experiment()

    with h5py.File(h5_path, "r") as f:
        attrs = dict(f["/data/RasteringGUI/raster"].attrs)
    assert attrs["point_index"] == 3
    assert list(attrs["target_xy"]) == [1.5, 2.5]
    # Pins the whole GUI->h5 hop: target_xy is uninterpretable without knowing
    # whether it is pixels or motor mm.
    assert attrs["frame"] == "pixel"


def test_comms_disabled_shot_does_not_restamp_the_previous_shot(tmp_path):
    """With comms off, transition_to_buffered returns before it assigns
    h5_filepath, and _raster_meta deliberately survives the shot group. A
    stale path would send the stamp back into the already-finished shot."""
    w, first = _shot_worker(tmp_path, "first.h5")
    w.transition_to_buffered("RasteringGUI", str(first), {}, True)
    with h5py.File(first, "r+") as f:     # stand in for experiment_queue.py:910
        f["/"].require_group("data")
    w.post_experiment()

    with h5py.File(first, "r+") as f:     # BLACS never revisits a finished shot
        del f["/data"]

    w.enable_comms = False
    w.transition_to_buffered("RasteringGUI", str(tmp_path / "second.h5"), {}, True)
    w.post_experiment()

    with h5py.File(first, "r") as f:
        assert "data" not in f["/"]
