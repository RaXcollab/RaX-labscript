"""errorHandling(214) must raise NuvuTimeout WITHOUT closing the camera.
Regression for the 2026-07-06 214->101 cascade: closeCam on a frame-wait
timeout kills the handle, so post_experiment's get_cam_data() dies with
fatal 101 and the tab needs a full BLACS restart."""
import pytest

from user_devices.NuvuCamera.Nuvu_sdk.nc_camera import (
    NuvuException, NuvuTimeout, nc_camera,
)


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
