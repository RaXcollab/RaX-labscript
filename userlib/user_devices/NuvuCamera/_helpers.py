"""SDK-free pure-Python helpers for NuvuCamera (extracted per T6.1 audit).

These helpers do NOT import ``Nuvu_sdk``, so they can be loaded and unit-
tested in any environment that has the userlib path on ``sys.path``. The
hardware-bound counterparts live on ``NuvuCamera`` in ``blacs_workers.py``.

Test surface lives at ``userlib/user_devices/NuvuCamera/tests/test_helpers.py``.
"""
from __future__ import annotations


def apply_attribute_update(attrs, name, value):
    """Mutate ``attrs`` in place: ``attrs[name] = value``; return ``(name, value)``.

    Pure half of ``NuvuCamera.set_attribute``. The hardware-side
    ``camera_utils.set_attrs({name: value})`` call stays on the class because
    it dereferences the SDK handle.

    Returns the ``(name, value)`` pair so callers can chain or assert.
    """
    attrs[name] = value
    return (name, value)


# ---------------------------------------------------------------------------
# Nuvu SDK error-code classification (values are authoritative, from the vendor
# header C:\\Program Files\\Nuvu Cameras\\Includes\\nc_error.h).
# ---------------------------------------------------------------------------

#: code -> (symbolic name, human description). Only the codes this device
#: reasons about explicitly; everything else falls back to the SDK docs.
NUVU_ERROR_DESCRIPTIONS = {
    27: (
        "NC_ERROR_CAMERA_FOUND",
        "no camera found (powered off, CameraLink/USB cable disconnected, "
        "or the camera is not enumerable)",
    ),
    101: (
        "NC_ERROR_CAM_STRUCT_PTR",
        "invalid NcCam handle — the SDK was called on a closed/invalid camera "
        "(this is fallout from an earlier emergency close, not a root cause)",
    ),
    107: (
        "NC_ERROR_CAM_NO_FEATURE",
        "the requested feature is not supported by this camera; benign, the "
        "driver is left open",
    ),
    214: (
        "NC_ERROR_GRAB_TIMEOUT",
        "the image did not arrive before the configured timeout; benign "
        "frame-wait race, the camera is left open and the grab is retried",
    ),
    215: (
        "NC_ERROR_GRAB_NO_IMAGE",
        "no image available yet (null frame pointer); the camera handle "
        "remains valid, the driver is left open",
    ),
    216: (
        "NC_ERROR_GRAB_NOT_STOP",
        "acquisition still in progress when it should be stopped; the camera "
        "handle remains valid, the driver is left open",
    ),
}


def describe_error_code(code):
    """Return a human-readable description for a Nuvu SDK error code.

    Falls back to a pointer at the SDK header for codes not enumerated above.
    Pure/SDK-free so it can be used both in operator-facing messages and unit
    tests.
    """
    entry = NUVU_ERROR_DESCRIPTIONS.get(code)
    if entry is None:
        return f"unknown Nuvu error {code} (see nc_error.h in the Nuvu SDK)"
    name, desc = entry
    return f"{name} ({code}): {desc}"


# ---------------------------------------------------------------------------
# Camera-open retry/backoff (TASK 1). Bounded so worker init cannot hang.
# ---------------------------------------------------------------------------

CAMERA_OPEN_MAX_ATTEMPTS = 3
CAMERA_OPEN_BASE_DELAY_S = 3.0
CAMERA_OPEN_BACKOFF = 2.0
CAMERA_OPEN_MAX_DELAY_S = 5.0


def open_retry_delays(
    max_attempts=CAMERA_OPEN_MAX_ATTEMPTS,
    base_delay=CAMERA_OPEN_BASE_DELAY_S,
    backoff=CAMERA_OPEN_BACKOFF,
    max_delay=CAMERA_OPEN_MAX_DELAY_S,
):
    """Inter-attempt sleep durations (seconds) for camera-open retry.

    Returns a list of length ``max(0, max_attempts - 1)`` — one sleep between
    each pair of attempts, and none after the final attempt. Each delay is
    capped at ``max_delay`` so total added latency stays bounded. The default
    schedule is ``[3.0, 5.0]`` (8 s total added delay, well under 15 s).
    """
    delays = []
    delay = float(base_delay)
    for _ in range(max(0, max_attempts - 1)):
        delays.append(min(delay, max_delay))
        delay *= backoff
    return delays


def camera_open_failure_message(error, max_attempts=CAMERA_OPEN_MAX_ATTEMPTS):
    """Operator-facing message when the camera cannot be opened after retries.

    Names the likely causes (per SDK error 27 semantics) and the recovery
    action so the operator sees actionable guidance instead of a bare
    ``NuvuException: 27``.
    """
    return (
        "CHECK CAMERA POWER first — a powered off camera is the most common "
        f"cause (confirmed 2026-07-07). Nuvu camera could not be opened after "
        f"{max_attempts} attempts (last error: {error}). Also check the "
        "CameraLink/USB cable and that no other process is holding the Nuvu "
        "driver. Once powered/reconnected, click the tab restart button."
    )


# ---------------------------------------------------------------------------
# Manual-snap retry (TASK 2). Bounded retry of a single-frame acquisition.
# ---------------------------------------------------------------------------

SNAP_MAX_ATTEMPTS = 3


def snap_should_retry(attempt, max_attempts=SNAP_MAX_ATTEMPTS):
    """True if a manual snap that raised a frame-wait timeout (214) should be
    retried. ``attempt`` is the 1-based number of the attempt that just failed.
    """
    return attempt < max_attempts


def snap_timeout_message(max_attempts=SNAP_MAX_ATTEMPTS):
    """Operator-facing message when a manual snap times out on every attempt.

    Emphasises that the camera is still OPEN (no closed-handle cascade to
    error 101) and points at the likely cause.
    """
    return (
        f"Manual snap timed out (SDK 214) on all {max_attempts} attempts: no "
        "frame arrived within the camera timeout. The camera is still open "
        "(no driver close) — verify manual-mode trigger is internal "
        "(trigger_mode 0) and the exposure/timeout settings are sane, then "
        "try Snap again."
    )


# ---------------------------------------------------------------------------
# Continuous (live-view) resume decision (TASK 5). Idempotent resume of a
# paused live view.
# ---------------------------------------------------------------------------


def should_resume_continuous(continuous_dt, continuous_thread_running):
    """Return True iff a paused live view should be resumed.

    Resume when an interval is retained (``continuous_dt is not None`` — note
    ``0`` means "max rate" and is a valid, resumable interval) AND no
    continuous thread is currently running. The second clause makes resume
    idempotent: a redundant resume (e.g. ``abort()`` already re-started live
    view, then a pause-triggered ``transition_to_manual`` fires) returns
    False instead of double-starting the acquisition thread. Mirrors the guard
    in ``IMAQdxCameraWorker.abort()``.
    """
    return continuous_dt is not None and not continuous_thread_running
