# Handoff Prompts — Rastering Subsystem (Pathfinder 2026-06-09)

Copy-paste into `/make-plan`. U1 + U2 are already folded into the active session
plan (`~/.claude/plans/i-want-to-work-gleaming-cascade.md`, Phase 5 + Phase 3) —
these prompts are the standalone equivalents.

## U1 — Indexed path cursor + go-to-arbitrary-site

```
/make-plan Consolidate the two raster-stepping command paths in
GUIs/rastering/raster_controller.py into one indexed cursor, then add
"go to an arbitrary site on the path."

Unified component: indexed path model — self._raster_path_pts: List[TargetXY]
+ self._raster_index: int + one helper _next_raster_point_locked() (caller holds
_state_lock). Materialize once at start_raster via collect_points(it,
max_points=50000).

Rewrite these call sites (Pathfinder 01-flowcharts/runloop-stepping.md):
- raster_step (raster_controller.py:919-959): next(it) -> _next_raster_point_locked()
  inside one lock; build+enqueue after release.
- _enqueue_next_raster_point (raster_controller.py:1527-1551): same helper.
- start_raster (raster_controller.py:896): materialize list; _raster_total_steps=len.
- stop_raster/_finish_raster (:963): clear list/index instead of _raster_iter=None.
- ZMQ arm_raster predicate (_raster_iter is not None -> bool(_raster_path_pts));
  move_to_next (:1757) unchanged.

Then add select_path_index(n)/select_nearest_path_point(x,y) (no motion, emit
selection_changed_signal) and request_go_to_path_index(n) (motion via existing
request_move_target, tag 'move_target' NOT 'raster_step', sets _raster_index=n+1,
rejected mid-continuous-run).

Anti-patterns to reject: no PathModel/Strategy class (List+int+one helper); no
feature flag keeping the one-shot iterator; preserve Continuous + Step behavior
byte-for-byte (sequence-equivalence test required). Test pattern: call methods
unbound on a SimpleNamespace self with a real RLock, no Qt/no DLL (see
tests/test_command_queue.py). Work in worktree GUIs/rastering-stepping on
branch feat/raster-stepping.
```

## U2 — One target validation+transform + wire Display Bounds enforcement

```
/make-plan Consolidate the four duplicated motor-bounds checks in
GUIs/rastering/raster_controller.py _execute into one validation pipeline, and
re-enable the dead set_target_bounds() so the Automatic-Controls "Display
Bounds" box actually clamps motion.

Unified component: _validate_and_transform_target(target_xy, mode) ->
(motor_xy, MotorResult|None) doing target-bounds (if set) -> calibration
target_to_motor -> motor-bounds, with context-specific error wording via `mode`.

Rewrite these call sites (Pathfinder 02-duplication-report.md A2,
01-flowcharts/motor-queue.md):
- _execute branches at raster_controller.py:1205-1210, 1247-1252, 1311-1320,
  1336-1345 -> single _validate_and_transform_target() call each.
- Re-enable set_target_bounds() (currently commented near raster_controller.py:932)
  and have ui.py _display_bounds (ui.py:915) call controller.set_target_bounds()
  with the drawn xlow/xhigh/ylow/yhigh so the box == enforced target_bounds.

Anti-patterns to reject: no bounds-policy registry/strategy; straight-line checks;
no behavior change to the OK path — only the previously-cosmetic box becomes
enforcing. Add a test that an out-of-box target is rejected with ok=False.
Coordinate with U1 (both touch _execute / the move path).
```

## U3 — Camera-dock dedup (DEFERRED — gated on the camera-branch decision)

```
/make-plan (RUN ONLY AFTER deciding feat/spinnaker-gige) Consolidate camera-dock
blockSignals boilerplate: one _set_widget_silent(w,value) helper for AOI sync
(camera_settings_dock.py:403-425), timing-mode (ui.py:415-420,558-563),
rotation/flip (ui.py:509-517,1340-1348), backlash/home spinboxes
(ui.py:1142-1227); one _ROTATION_INDEX_TO_K constant (camera_settings_dock.py:438,
ui.py:283,508,1339); one clamp_frac() (camera_settings_dock.py:346,355,ui.py:1508).
NOTE: camera_settings_dock.py is heavily rewritten on feat/spinnaker-gige — if
that branch lands, redo this against the new dock, not main.
```
