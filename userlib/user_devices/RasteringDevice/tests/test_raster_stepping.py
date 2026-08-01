"""Raster stepping: arm-once, step every Nth shot, finished/reset semantics.

SDK-free: build the worker via __new__ (skip blacs Worker.__init__) and
exercise _advance_raster / update_raster_mode / _init_raster_state directly
(transition_to_buffered's raster block delegates to _advance_raster; the
rest of it is h5 programming, untouched here).
"""
import logging

import pytest

from user_devices.RasteringDevice.blacs_workers import RasteringWorker


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


# --- finished=True resets armed+counter, next queue re-arms ---

def test_finished_raises_and_resets_for_rearm():
    replies = {"arm_raster": ARMED_STEP, "move_to_next": FINISHED}
    w = make_worker(shots_per_step=3, replies=replies)
    with pytest.raises(Exception, match="sequence complete"):
        w._advance_raster()
    assert w._raster_armed is False and w._shots_since_step == 0
    # Re-queue: arms again from scratch
    w.remote_comms.replies["move_to_next"] = SUCCESS
    w._advance_raster()
    assert len(w.remote_comms.sent("arm_raster")) == 2


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
