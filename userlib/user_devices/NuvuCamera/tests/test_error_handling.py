"""errorHandling(214) must raise NuvuTimeout WITHOUT closing the camera.
Regression for the 2026-07-06 214->101 cascade: closeCam on a frame-wait
timeout kills the handle, so post_experiment's get_cam_data() dies with
fatal 101 and the tab needs a full BLACS restart."""
import pytest

try:
    from user_devices.NuvuCamera.Nuvu_sdk.nc_camera import (
        NuvuException, NuvuTimeout, nc_camera,
    )
except (ImportError, OSError) as exc:
    # NC_api loads nc_driver_x64.dll at import time. On checkouts without the
    # Nuvu driver (laptops, CI) the pre-push hook still collects this file —
    # skip cleanly instead of blocking every push with a loader error.
    pytest.skip(f"Nuvu SDK unavailable: {exc}", allow_module_level=True)


def _blacs_workers():
    """Import and return the NuvuCamera ``blacs_workers`` module.

    pytest's default "prepend" import mode puts this test package's parent
    directory (``…/user_devices/NuvuCamera/``, which has no ``__init__.py``) on
    ``sys.path``, and that directory holds a local ``labscript_devices.py`` that
    would shadow the *installed* ``labscript_devices`` package which
    ``blacs_workers.py`` imports at module scope
    (``ModuleNotFoundError: … 'labscript_devices' is not a package``). BLACS only
    ever puts ``userlib/`` on the path, so the shadow never happens in
    production. Drop that entry here so the real backend package resolves.

    Done at call time (after collection completes), NOT at import/conftest time:
    importing ``blacs_workers`` pulls in ``labscript_utils`` and activates its
    ``double_import_denier``; doing that during collection would retro-trip the
    denier on sibling dual-path test packages (e.g. NI_SCOPE) in the combined
    pre-push run.
    """
    import os
    import sys
    _pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path[:] = [p for p in sys.path if os.path.abspath(p) != _pkg_dir]
    from user_devices.NuvuCamera import blacs_workers
    return blacs_workers


def _bare_cam():
    cam = nc_camera.__new__(nc_camera)      # no SDK open
    cam.close_calls = []
    cam.closeCam = lambda noRaise=False: cam.close_calls.append(noRaise)
    class _L:                                # logger stub
        def debug(self, *a, **k): pass
    cam.logger = _L()
    return cam


def test_214_raises_timeout_and_keeps_camera_open():
    cam = _bare_cam()
    with pytest.raises(NuvuTimeout):
        cam.errorHandling(214)
    assert cam.close_calls == []             # handle NOT closed


def test_timeout_is_a_nuvu_exception():
    assert issubclass(NuvuTimeout, NuvuException)


def test_other_codes_still_close_and_raise():
    cam = _bare_cam()
    with pytest.raises(NuvuException):
        cam.errorHandling(131)
    assert cam.close_calls == [True]         # closeCam(noRaise=True) preserved


def test_107_is_benign_no_close_no_raise():
    """NC_ERROR_CAM_NO_FEATURE (107): feature not supported by this camera.
    Must return WITHOUT closing the driver and WITHOUT raising — previously the
    `if error == 107: pass` fell through to the else branch and closed the
    camera, cascading to error 101 (invalid handle) on the next SDK call."""
    cam = _bare_cam()
    assert cam.errorHandling(107) is None    # returns, does not raise
    assert cam.close_calls == []             # handle NOT closed


def test_27_raises_without_closing():
    """Camera-not-found (27) raises NuvuException but does not close the driver
    (there is nothing open to close)."""
    cam = _bare_cam()
    with pytest.raises(NuvuException):
        cam.errorHandling(27)
    assert cam.close_calls == []


def test_215_216_grab_conditions_raise_without_closing():
    """Grab-family conditions (215 no-image-yet, 216 not-stopped) leave the
    NcCam handle valid — raise WITHOUT closing, so no close->101 cascade."""
    for code in (215, 216):
        cam = _bare_cam()
        with pytest.raises(NuvuException):
            cam.errorHandling(code)
        assert cam.close_calls == []         # handle NOT closed


# ---------------------------------------------------------------------------
# TASK 2 — manual-snap 214 protection
# ---------------------------------------------------------------------------

class _L:
    def debug(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def info(self, *a, **k):
        pass


def test_snap_retries_on_timeout_then_succeeds():
    bw = _blacs_workers()

    class _FakeUtils:
        def __init__(self):
            self.calls = 0

        def get_image(self):
            self.calls += 1
            if self.calls < 2:
                raise NuvuTimeout("214")
            return "frame"

    class _FakeCam:
        def __init__(self):
            self.camera_utils = _FakeUtils()
            self.configure_calls = 0
            self.stop_calls = 0
            self.logger = _L()

        def configure_acquisition(self, continuous=False, bufferCount=0):
            self.configure_calls += 1

        def stop_acquisition(self):
            self.stop_calls += 1

    cam = _FakeCam()
    snap = bw.NuvuCamera.snap.__get__(cam)
    assert snap() == "frame"
    assert cam.camera_utils.calls == 2   # timed out once, succeeded on retry
    assert cam.configure_calls == 2      # re-armed the single-frame acquisition
    assert cam.stop_calls == 1           # stop only on success


def test_snap_raises_clean_timeout_after_exhausting_retries():
    bw = _blacs_workers()
    from user_devices.NuvuCamera._helpers import SNAP_MAX_ATTEMPTS

    class _FakeUtils:
        def __init__(self):
            self.calls = 0

        def get_image(self):
            self.calls += 1
            raise NuvuTimeout("214")

    class _FakeCam:
        def __init__(self):
            self.camera_utils = _FakeUtils()
            self.stop_calls = 0
            self.logger = _L()

        def configure_acquisition(self, continuous=False, bufferCount=0):
            pass

        def stop_acquisition(self):
            self.stop_calls += 1

    cam = _FakeCam()
    snap = bw.NuvuCamera.snap.__get__(cam)
    with pytest.raises(NuvuTimeout):
        snap()
    assert cam.camera_utils.calls == SNAP_MAX_ATTEMPTS  # bounded number of tries
    assert cam.stop_calls == 1  # best-effort disarm after the final failure


# ---------------------------------------------------------------------------
# TASK 5 — idempotent continuous-view resume
# ---------------------------------------------------------------------------

def _fake_worker(**attrs):
    class _FakeWorker:
        pass
    w = _FakeWorker()
    w.logger = _L()
    w.manual_mode_camera_attributes = {}
    w.set_attributes_smart = lambda a: None
    w.start_calls = []
    w.start_continuous = lambda dt: w.start_calls.append(dt)
    for k, v in attrs.items():
        setattr(w, k, v)
    return w


def test_transition_to_manual_resumes_paused_liveview_once():
    bw = _blacs_workers()
    w = _fake_worker(continuous_dt=0, continuous_thread=None)  # paused, max rate
    t2m = bw.NuvuCameraWorker.transition_to_manual.__get__(w)
    assert t2m() is True
    assert w.start_calls == [0]     # resumed exactly once with the retained dt


def test_transition_to_manual_does_not_double_resume():
    bw = _blacs_workers()
    # abort() already re-started live view (thread set) before this
    # pause-triggered transition_to_manual fires:
    w = _fake_worker(continuous_dt=5.0, continuous_thread=object())
    t2m = bw.NuvuCameraWorker.transition_to_manual.__get__(w)
    assert t2m() is True
    assert w.start_calls == []      # no redundant resume


def test_transition_to_manual_no_resume_when_liveview_never_ran():
    bw = _blacs_workers()
    w = _fake_worker(continuous_dt=None, continuous_thread=None)
    t2m = bw.NuvuCameraWorker.transition_to_manual.__get__(w)
    assert t2m() is True
    assert w.start_calls == []


def test_start_continuous_idempotent_noop_when_already_running():
    bw = _blacs_workers()

    class _FakeWorker:
        pass

    w = _FakeWorker()
    w.logger = _L()
    w.continuous_thread = object()  # already running
    # camera intentionally absent: a correct no-op must not touch it.
    start = bw.NuvuCameraWorker.start_continuous.__get__(w)
    assert start(0) is None


def test_grab_multiple_retries_on_timeout_then_succeeds():
    bw = _blacs_workers()

    class _FakeCam:
        """grab() times out twice, then returns a frame."""
        def __init__(self):
            self.calls = 0
            self._abort_acquisition = False
        def grab(self):
            self.calls += 1
            if self.calls < 3:
                raise NuvuTimeout("214")
            return "frame"

    # bind the real (patched) grab_multiple onto the fake. grab_multiple lives
    # on the NuvuCamera interface class (NOT NuvuCameraWorker):
    cam = _FakeCam()
    grab_multiple = bw.NuvuCamera.grab_multiple.__get__(cam)
    class _L:
        def debug(self, *a, **k): pass
    cam.logger = _L()
    images = []
    grab_multiple(1, images)
    assert images == ["frame"]
    assert cam.calls == 3


def test_grab_multiple_abort_wins_over_retry():
    bw = _blacs_workers()

    class _FakeCam:
        """grab() times out AND abort is signalled during the frame wait."""
        def __init__(self):
            self.calls = 0
            self._abort_acquisition = False
        def grab(self):
            self.calls += 1
            # Abort raised (e.g. by abort_acquisition) while we were waiting:
            self._abort_acquisition = True
            raise NuvuTimeout("214")

    cam = _FakeCam()
    grab_multiple = bw.NuvuCamera.grab_multiple.__get__(cam)
    class _L:
        def debug(self, *a, **k): pass
    cam.logger = _L()
    images = []
    grab_multiple(1, images)
    assert images == []                        # abort exits before another grab
    assert cam._abort_acquisition is False     # loop reset the flag
    assert cam.calls == 1                       # no retry after abort was seen
