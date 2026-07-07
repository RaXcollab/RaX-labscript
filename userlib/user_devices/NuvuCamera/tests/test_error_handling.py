"""errorHandling(214) must raise NuvuTimeout WITHOUT closing the camera.
Regression for the 2026-07-06 214->101 cascade: closeCam on a frame-wait
timeout kills the handle, so post_experiment's get_cam_data() dies with
fatal 101 and the tab needs a full BLACS restart."""
import pytest

from user_devices.NuvuCamera.Nuvu_sdk.nc_camera import (
    NuvuException, NuvuTimeout, nc_camera,
)


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
