# Known Latent Issues

> **Scope**: code-quality issues + latent bugs discovered during the 2026-05-19 priming pass. None are runtime bugs on this PC today — they are conditional bugs that fire only when specific code paths get exercised. Cataloged here so future sessions don't trip over them. **No fixes recommended for routine work** unless the relevant feature is being revived.

This doc is the persistent record. Each entry: what / where / severity / when it matters / fix sketch. Refresh after each priming pass.

---

## NuvuCamera — ctypes signature mis-assignment (FIXED 2026-05-19)

**Where**: `userlib/user_devices/NuvuCamera/Nuvu_sdk/NC_api.py`

**What**: Two `restype` / `argtypes` assignment lines were stranded after the wrong function definitions, registering bogus C signatures on `ncCamGetBinningMode` and `ncCamGetComponentTemp`. Fixed in the 2026-05-19 refactor; if you see this resurface (e.g., regen from upstream SDK update), re-check.

**Severity**: HIGH when NuvuCamera path is exercised — getters would return silently wrong values (no exception, just garbage). LATENT on this PC because NuvuCamera is currently not in the active connection table.

**Fix verification**: `grep -A2 "ncCamGetBinningMode\|ncCamGetComponentTemp" userlib/user_devices/NuvuCamera/Nuvu_sdk/NC_api.py` should show `restype` / `argtypes` correctly bound to each function.

---

## NuvuCamera — 215/216 no-close guarantee holds in `errorHandling` but not through `disconnect_if_error_real`

**Where**: `userlib/user_devices/NuvuCamera/Nuvu_sdk/Nuvu_cam_utils.py` (`disconnect_if_error_real`, ~lines 75-89) vs `nc_camera.py` `errorHandling` 215/216 branch (added 2026-07-08).

**What**: `errorHandling` raises 215 (`NC_ERROR_GRAB_NO_IMAGE`) / 216 (`NC_ERROR_GRAB_NOT_STOP`) without closing the camera, but on the manual `get_image` path the `disconnect_if_error_real` decorator spares only `NuvuTimeout` — a `NuvuException(215/216)` falls to its generic `except Exception` and closes the camera anyway. The buffered path (`get_queued_image`, no-op decorator) gets the full no-close benefit.

**Severity**: LATENT-LOW — 215/216 have never been observed on this hardware (2 days of logs swept 2026-07-08). Even if one fires during manual operation, behavior is strictly better than pre-2026-07-08 (single clean close with the real message preserved, vs the old triple-close that masked the original error).

**When it matters**: only if 215/216 starts occurring during manual snap / live view.

**Fix sketch**: add a `NuvuTimeout`-sibling subclass (e.g. `NuvuGrabCondition`) raised by the 215/216 branch and spared by the decorator. The string-in-`.error` convention means the decorator can't cheaply check the numeric code, so the subclass is the clean route. (Audit ref: 2026-07-08 blacs-expert re-audit, finding 3.)

---

## `labscript-devices/AlazarTechBoard.py` — uses `time.clock()` (removed in Py3.8+)

**Where**: `labscript-devices/labscript_devices/AlazarTechBoard.py`

**What**: Calls `time.clock()` which was removed in Python 3.8. First invocation will `AttributeError: module 'time' has no attribute 'clock'`.

**Severity**: LATENT — file is unused on this PC; no Alazar digitizers in active CT.

**When it matters**: when (if) Alazar digitizers are revived. The first acquisition timestamp call will fault.

**Fix sketch**: replace `time.clock()` → `time.perf_counter()`. Single-line change per call site (likely 2–3 sites). Trivial — but only do this if you're actively bringing Alazar back online; otherwise leave the latent reminder here.

---

## `labscript-devices/imaqdx_server.py` — pre-h5py-3 APIs

**Where**: `labscript-devices/labscript_devices/imaqdx_server.py`

**What**: Two pre-modern-Python idioms:
- `h5_file['...'].value` accessor — removed in h5py 3.0; current API is `dset[()]`.
- `option is 'image_path'` — string identity compare; works by CPython interning but is officially wrong (use `==`).

**Severity**: LATENT — file is superseded by the in-process `IMAQdxCameraWorker`. The legacy standalone-server pattern is not used.

**When it matters**: never, in practice. If someone tries to revive the standalone IMAQdx camera-server architecture, all `.value` accesses and `is` compares will need updating before it runs on this Python 3.11 stack.

**Fix sketch**: `.value` → `[()]`, `is` → `==`. Don't bother unless reviving the pattern — the in-process worker is strictly better.

---

## `labscript-utils/.../device_registry/_device_registry.py` — uses `import imp`

**Where**: `labscript-utils/labscript_utils/device_registry/_device_registry.py`

**What**: Imports the `imp` module. `imp` was removed in Python 3.12.

**Severity**: LATENT — fine on this PC's Python 3.11.

**When it matters**: **Python upgrade insurance.** On Python 3.12, BLACS will fail to load any device with `register_classes.py` (which is ALL custom userlib devices: LaserLockGUI, RasteringGUI, BigSkyLasers, etc.). Hard upgrade blocker.

**Fix sketch**: replace with `importlib.util.spec_from_file_location` + `module_from_spec` + `spec.loader.exec_module`. ~15-line change. Worth doing while in context — see Tier 5.3 of the 2026-05-19 refactor plan.

---

## BigSky `LASER_SN_TO_CONNECTION = {}` empty placeholder (FIXED 2026-05-19)

**Where**: `GUIs/BigSkyControl/HugeSkyController.pyw` ~line 248

**What**: SN → connection-name mapping was empty `{}`; fallback was `_laserLaunchOrder` monotonic counter. Behavior was deterministic-by-accident (stable Windows COM-port enumeration). Populated in 2026-05-19 refactor with `{'151': 'YAG_1', '213': 'YAG_2'}`.

**Severity**: LATENT until populated; **MEDIUM otherwise** — if Windows ever re-enumerates COM ports (driver update, USB hub change, cable swap, third laser added), counter would silently assign the wrong physical laser → BLACS sends `YAG_1_voltage` to the wrong YAG.

**When it matters**: physical laser swap, hub-restart-in-different-order, new laser added.

**Fix verification**: `grep -A4 "LASER_SN_TO_CONNECTION = {" GUIs/BigSkyControl/HugeSkyController.pyw` should show populated entries. If `{}` reappears (e.g., merge conflict), re-populate.

---

## BigSky Setter Verify Gap

**Where**: `GUIs/BigSkyControl/BigSkyControllerAmbitious.py` — `SingleLaserController._setQSwitchInternal`, `_setQSwitchBurst`, `_setQSwitchExternal`, `_remoteSetVoltage`, shutter / qswitch setters.

**What**: Only `_setLampMode` parses + verifies the controller response (`_TRAILING_INT_RE` regex on the `>cg`-style reply + mismatch handling). All other setters cache the requested value without verifying acceptance.

**Severity**: MEDIUM — if a serial write succeeds but hardware silently rejects (out-of-range voltage, mode-change refused), cache and reality drift for up to ~10 s until next `check_remote_values` resync. For a pulsed Nd:YAG with energy / safety implications and BLACS-side strict `COMMAND_ORDER` enforcement, that's a real reproducibility / safety window.

**When it matters**: any time hardware silently rejects a setpoint. Out-of-range voltage is the most likely trigger.

**Fix sketch**: extend the `_setLampMode` parse-verify pattern to all `_set*` methods. ~6–8 methods × ~10 lines each. NOT in the 2026-05-19 refactor scope (user explicitly skipped — would "slow down non-essential steps"). Document the gap; revisit if data-integrity drift becomes observed.

---

## `_laserLaunchOrder` never decremented

**Where**: `GUIs/BigSkyControl/HugeSkyController.pyw`, `MyTableWidget.__init__` line 393 (`self._laserLaunchOrder = 0`) and line 412 (`self._laserLaunchOrder += 1`).

**What**: Counter increments on every new tab; never decrements on close. Open Tab1 (YAG_1) → Tab2 (YAG_2) → close Tab1 → open new tab → that new tab becomes YAG_3, NOT YAG_1.

**Severity**: LOW — intentional design (prevents re-binding the same name to a different physical laser mid-session). Resets to 0 on hub restart.

**When it matters**: now moot — `LASER_SN_TO_CONNECTION` is populated (2026-05-19), so connection names come from the dict, not the counter. The counter is only fallback for unmapped SNs.

**Verdict**: not a bug. Document only.

---

## NI_SCOPE stale log strings (FIXED 2026-05-19)

**Where**: `userlib/user_devices/NI_SCOPE/blacs_workers.py`

**What**: Print / log strings said "50%" or "start-trigger" while `ref_position=0` and trigger source is configurable from connection-table properties. Confusing for log triage.

**Severity**: LOW (cosmetic / observability).

**Fix verification**: BLACS.log strings now reflect `self.ref_position` / `self.trigger_source` dynamically.

---

## Commented-out legacy blocks in NI_SCOPE and edge_counter

**Where**: `userlib/user_devices/NI_SCOPE/labscript_devices.py`, `userlib/user_devices/NI_SCOPE/blacs_workers.py`, `userlib/user_devices/edge_counter/...`

**What**: Large blocks of prior implementations alongside live code. Adds noise during reads.

**Severity**: LOW (hygiene, not functional).

**Fix**: delete; git history preserves them.

**Why not done now**: user explicitly skipped in 2026-05-19 ("leave it") — low priority. Revisit if these files get a substantive rewrite.

---

## `userlib/user_devices/__init__ .py` (literal space in filename)

**Where**: as written — note the space before `.py`.

**What**: Intentional stub per its own comment ("DO NOT import `register_classes` here"). The space in the filename makes it un-importable as a module — `from user_devices import __init__` would fail. This is deliberate: the file exists as a comment-only marker.

**Severity**: zero. Not a bug.

**Verdict**: leave it. Document only because the filename is confusing on first encounter.

---

## See also

- `docs/blacs-state-machine.md` — fork-specific lifecycle (separate doc; latched-lines pattern lives there, not here, because it's a fork feature not a latent bug).
- `docs/external-guis-architecture.md` — per-GUI architecture (BigSky Setter Verify Gap context).
- `.claude/rules/devices.md` — load-bearing per-shot teardown + latched-lines invariants.
- Auto-memory references for resolved issues:
  - [[reference_two-remotecontrol-trees]] — the dual-tree situation isn't a bug, but the labscript-devices copy IS dead code.
  - [[reference_bigsky-controller-split]] — the file split isn't a bug, but you have to know about it.
  - [[reference_post-experiment-vs-transition-to-manual]] — the lifecycle invariant that prevents many would-be bugs.
