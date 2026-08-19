# Rastering GUI Progressive-Slowdown Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the rastering GUI from slowing down over multi-hour sessions by recording position-history *changes* instead of poll ticks, and harden the two unbounded sinks that turn any slowdown into a spiral (log pane, camera-frame event queue).

**Architecture:** Three independent guards in `GUIs/rastering/ui.py`, no protocol or controller changes. (1) `_on_target_position` gets a last-point dedup so the ~4 Hz telemetry poll (READ_POS, `config.py:58`) no longer appends duplicate points — evidence: `Logs/position_history_20260810_211138.csv` has 164,244 rows but only 222 unique positions, and `ScatterPlotItem.setData` at 164k points measures 297 ms + 119 ms paint (bench: session scratchpad `scatter_bench.py`). (2) The log pane document gets a max block count. (3) Camera frames are coalesced drop-to-latest via an O(1) store slot + a GUI-thread render timer, so a busy GUI thread can never accumulate queued 1.3 MB frame events.

**Tech Stack:** PyQt5, pyqtgraph, pytest (unbound-method + duck-typed `SimpleNamespace` self pattern from `tests/test_command_queue.py`).

## Global Constraints

- All Python runs in conda env **`rastering`**: `source ~/miniconda/etc/profile.d/conda.sh && conda activate rastering`
- `GUIs/rastering` is the **live** worktree of `RaXcollab/rastering` on `main` — the operator runs it between shots. All work happens on the topic-branch worktree created in Task 1; merge to `main` only at the Task 5 checkpoint with explicit user confirmation.
- **Never `git push`** — pushing needs explicit user approval.
- **Never run ui-importing tests (`tests/test_ui_slowdown_guards.py`, `test_command_queue.py`, `test_raster_goto_handlers.py`) while the rastering GUI is running** — they open the uEye camera and hang. Check first (empty output = safe):
  `Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -match 'main_rastering' }`
- Camera-safe suites `tests/test_raster_pathmodel.py` and `tests/test_zmq_v2_protocol.py` must BOTH pass before every commit (repo rule).
- Do not touch `calibration_data.json` in any worktree; **never** `git restore` it (wipes live operator calibration).
- One git mutation per shell call (Windows git race).
- Main-thread QTimers stay on the default **CoarseTimer** — never set `Qt.PreciseTimer` on the Windows GUI thread.
- Commit messages end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: Topic-branch worktree + green baseline

**Files:**
- Create: `GUIs/rastering-slowdown-fix/` (git worktree, branch `fix/gui-slowdown-history-dedup`)

**Interfaces:**
- Produces: worktree path `C:\Users\radmo\labscript-suite\GUIs\rastering-slowdown-fix` — all later tasks edit/test/commit THERE, not in `GUIs/rastering`.

- [ ] **Step 1: Survey the rastering repo (read-only)**

```bash
cd /c/Users/radmo/labscript-suite/GUIs/rastering && git status --short && git worktree list && git branch -vv
```

Expected: on `main`; dirty `calibration_data.json`/`camera_params.ini` churn is normal — leave it alone. If anything ELSE is dirty, stop and surface to the user before proceeding.

- [ ] **Step 2: Create the topic-branch worktree**

```bash
cd /c/Users/radmo/labscript-suite/GUIs/rastering && git worktree add ../rastering-slowdown-fix -b fix/gui-slowdown-history-dedup
```

- [ ] **Step 3: Baseline — camera-safe suites pass in the worktree**

```bash
cd /c/Users/radmo/labscript-suite/GUIs/rastering-slowdown-fix && source ~/miniconda/etc/profile.d/conda.sh && conda activate rastering && python -m pytest tests/test_raster_pathmodel.py tests/test_zmq_v2_protocol.py -q
```

Expected: all pass. If not, stop — pre-existing breakage must be surfaced, not fixed in this plan.

---

### Task 2: Dedup guard in `_on_target_position` (root cause)

**Files:**
- Modify: `GUIs/rastering-slowdown-fix/ui.py:2202-2218` (`_on_target_position`)
- Test: create `GUIs/rastering-slowdown-fix/tests/test_ui_slowdown_guards.py`

**Interfaces:**
- Consumes: `RasterMainWindow._on_target_position(self, x: float, y: float) -> None` (existing slot, signature unchanged).
- Produces: same slot, new behavior — a point is appended to `self._history` / written to the CSV / scatter-refreshed **only when `(float(x), float(y))` differs from `self._history[-1]`**. Task 3's test file additions build on the same test module created here.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ui_slowdown_guards.py`:

```python
"""Guards against the 2026-08-11 progressive-slowdown class of bugs.

Root cause then: the ~4 Hz telemetry poll fed _on_target_position, which
appended EVERY tick to self._history and redrew the full scatter each time
(position_history_20260810_211138.csv: 164,244 rows, 222 unique positions;
ScatterPlotItem.setData at 164k pts = ~300 ms on this machine).

CAMERA CAVEAT (same as test_command_queue.py): importing ui.py pulls in
PyQt5 + pyueye. Never run while the rastering GUI is running. Skips
cleanly where ui.py is not importable.

Standalone-runnable:
    conda activate rastering && python tests/test_ui_slowdown_guards.py
"""

from __future__ import annotations

import os
import sys
import types
from unittest import mock

# ui.py lives one level up from tests/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import ui  # noqa: E402
    _UI_IMPORT_ERROR = None
except Exception as e:  # noqa: BLE001
    ui = None
    _UI_IMPORT_ERROR = e


def _require_ui():
    if ui is None:
        import pytest
        pytest.skip(f"ui.py not importable here: {_UI_IMPORT_ERROR}")


def _target_position_self(save_checked: bool = True) -> types.SimpleNamespace:
    """Duck-typed `self` carrying ONLY what _on_target_position touches.

    Same unbound-method pattern as test_command_queue.py: the REAL method
    body runs with zero hardware and no Qt event loop.
    """
    return types.SimpleNamespace(
        current_target_marker=mock.Mock(name="current_target_marker"),
        checkBox_2=types.SimpleNamespace(isChecked=lambda: save_checked),
        _history=[],
        _pos_history_file=None,
        _pos_history_write_warned=False,
        _refresh_manual_scatter=mock.Mock(name="_refresh_manual_scatter"),
        _log=mock.Mock(name="_log"),
    )


def test_idle_poll_repeats_are_not_recorded():
    """The telemetry poll repeats the same position ~4x/s while the motor
    is idle. Only the FIRST occurrence may be recorded."""
    _require_ui()
    fake = _target_position_self()
    for _ in range(3):
        ui.RasterMainWindow._on_target_position(fake, 1.0, 2.0)
    assert fake._history == [(1.0, 2.0)]
    assert fake._refresh_manual_scatter.call_count == 1


def test_position_changes_are_recorded():
    _require_ui()
    fake = _target_position_self()
    ui.RasterMainWindow._on_target_position(fake, 1.0, 2.0)
    ui.RasterMainWindow._on_target_position(fake, 1.0, 2.0)
    ui.RasterMainWindow._on_target_position(fake, 3.5, 4.5)
    assert fake._history == [(1.0, 2.0), (3.5, 4.5)]
    assert fake._refresh_manual_scatter.call_count == 2


def test_csv_written_only_on_change():
    _require_ui()
    fake = _target_position_self()
    fake._pos_history_file = mock.Mock(name="pos_history_file")
    for _ in range(3):
        ui.RasterMainWindow._on_target_position(fake, 1.0, 2.0)
    assert fake._pos_history_file.write.call_count == 1


def test_unchecked_records_nothing_but_marker_still_moves():
    _require_ui()
    fake = _target_position_self(save_checked=False)
    ui.RasterMainWindow._on_target_position(fake, 1.0, 2.0)
    assert fake._history == []
    fake.current_target_marker.setData.assert_called_once_with([1.0], [2.0])


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failures else 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/Users/radmo/labscript-suite/GUIs/rastering-slowdown-fix && conda activate rastering && python -m pytest tests/test_ui_slowdown_guards.py -v`
Expected: `test_idle_poll_repeats_are_not_recorded`, `test_position_changes_are_recorded`, `test_csv_written_only_on_change` FAIL (current code appends every call); `test_unchecked_records_nothing_but_marker_still_moves` PASSES (behavior already correct — it pins it).

- [ ] **Step 3: Implement the dedup guard**

In `ui.py`, replace the body of `_on_target_position` (currently lines 2202-2218):

```python
    def _on_target_position(self, x: float, y: float) -> None:
        # Update current marker + history
        self.current_target_marker.setData([x], [y])

        if self.checkBox_2.isChecked():  # Save position history
            pt = (float(x), float(y))
            # The telemetry poll (~4 Hz) repeats the SAME position while the
            # motor is idle; recording every tick grew _history to 164k
            # entries (222 unique) over a 12 h session and the full-scatter
            # redraw below froze the GUI (2026-08-11 root cause). Record
            # position CHANGES only. Known ceiling: exact float equality --
            # if a future encoder jitters at rest, dedup stops matching;
            # today's hardware returns bit-identical idle reads (CSV proof).
            if not self._history or self._history[-1] != pt:
                self._history.append(pt)
                f = getattr(self, "_pos_history_file", None)
                if f is not None:
                    try:
                        f.write(f"{time.time()},{x},{y}\n")
                        f.flush()
                    except Exception as e:
                        if not getattr(self, "_pos_history_write_warned", False):
                            self._pos_history_write_warned = True
                            self._log(f"Position-history write failed (further errors suppressed): {e}")
                self._refresh_manual_scatter()
```

Notes for the implementer:
- `_refresh_manual_scatter()` moves INSIDE the changed-branch. This is safe: Last-N / Display-points widget changes trigger their own refresh (`ui.py:1183-1184`), and `_clear_manual_points` (`ui.py:1291`) clears `manual_scatter` directly.
- The CSV now records position *changes* only — that is the point of the fix, not a regression (the old files were 99.9% duplicate rows).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ui_slowdown_guards.py -v` (same dir/env)
Expected: all 4 PASS.

- [ ] **Step 5: Camera-safe suites still green, then commit**

Run: `python -m pytest tests/test_raster_pathmodel.py tests/test_zmq_v2_protocol.py -q`
Expected: all pass. Then:

```bash
cd /c/Users/radmo/labscript-suite/GUIs/rastering-slowdown-fix && git add ui.py tests/test_ui_slowdown_guards.py && git commit -m "fix(ui): record position-history CHANGES, not 4 Hz poll ticks

The telemetry READ_POS poll fed _on_target_position every ~250 ms; with
'Save position history' on, _history grew unbounded (164k entries / 222
unique in one 12 h session) and the per-tick full-scatter redraw
progressively froze the GUI, backing up 1.3 MB camera-frame events.
Dedup against the last recorded point; CSV + scatter refresh now fire
only on actual position changes.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Camera frame coalescing (drop-to-latest)

**Files:**
- Modify: `GUIs/rastering-slowdown-fix/ui.py:621` (connect), `ui.py:637` (after `camera_thread.start()`), new methods after `set_frame` (before `closeEvent`, currently line 282), `closeEvent` (line 282-293)
- Test: extend `GUIs/rastering-slowdown-fix/tests/test_ui_slowdown_guards.py`

**Interfaces:**
- Consumes: `UEyeCameraThread.new_frame` (pyqtSignal(np.ndarray), `camera.py:497`); `RasterMainWindow.set_frame(frame)` (unchanged, `ui.py:230`).
- Produces: `RasterMainWindow._store_frame(self, frame) -> None` (O(1) slot, connected to `new_frame`); `RasterMainWindow._render_latest_frame(self) -> None` (timer slot, calls `set_frame` with the newest pending frame or does nothing); `self._latest_frame`, `self._frame_timer` attributes.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_ui_slowdown_guards.py`)

```python
def _frame_self() -> types.SimpleNamespace:
    return types.SimpleNamespace(
        _latest_frame=None,
        set_frame=mock.Mock(name="set_frame"),
    )


def test_frames_coalesce_to_latest():
    """Two frames arrive while the GUI is busy; one render tick must show
    only the NEWEST -- older frames are dropped, never queued."""
    _require_ui()
    fake = _frame_self()
    ui.RasterMainWindow._store_frame(fake, "frame1")
    ui.RasterMainWindow._store_frame(fake, "frame2")
    ui.RasterMainWindow._render_latest_frame(fake)
    fake.set_frame.assert_called_once_with("frame2")


def test_render_with_no_pending_frame_is_a_noop():
    _require_ui()
    fake = _frame_self()
    ui.RasterMainWindow._render_latest_frame(fake)
    fake.set_frame.assert_not_called()


def test_render_consumes_the_frame():
    """A frame renders exactly once -- the next tick must not re-render it."""
    _require_ui()
    fake = _frame_self()
    ui.RasterMainWindow._store_frame(fake, "frame1")
    ui.RasterMainWindow._render_latest_frame(fake)
    ui.RasterMainWindow._render_latest_frame(fake)
    assert fake.set_frame.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ui_slowdown_guards.py -v`
Expected: the three new tests FAIL with `AttributeError: ... has no attribute '_store_frame'`; Task 2's four tests still PASS.

- [ ] **Step 3: Implement coalescing**

3a. In `_start_camera`, replace line 621 `self.camera_thread.new_frame.connect(self.set_frame)` with:

```python
        self.camera_thread.new_frame.connect(self._store_frame)
```

3b. In `_start_camera`, immediately after `self.camera_thread.start()` (line 637), add:

```python
        # Frame coalescing: the camera thread can outpace a busy GUI thread;
        # the old direct queued connection then accumulated 1.3 MB frame
        # events without bound (2026-08-11 slowdown spiral). _store_frame is
        # O(1), so the event queue always drains; rendering happens at most
        # once per timer tick, always with the newest frame. Default timer
        # type (CoarseTimer) on purpose -- never PreciseTimer on the Windows
        # GUI thread.
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_timer = QtCore.QTimer(self)
        self._frame_timer.setInterval(40)  # ~25 fps ceiling; camera delivers ~13.3
        self._frame_timer.timeout.connect(self._render_latest_frame)
        self._frame_timer.start()
```

3c. Add the two methods directly after `set_frame` (before `closeEvent`, currently line 282):

```python
    def _store_frame(self, frame: np.ndarray) -> None:
        """Camera-thread frames land here (queued connection). O(1): the
        newest frame wins; _render_latest_frame paints it on its own tick."""
        self._latest_frame = frame

    def _render_latest_frame(self) -> None:
        frame, self._latest_frame = self._latest_frame, None
        if frame is not None:
            self.set_frame(frame)
```

3d. In `closeEvent` (line 282), stop the timer before stopping the camera thread — insert as the FIRST statement of the method body:

```python
        try:
            if hasattr(self, "_frame_timer"):
                self._frame_timer.stop()
        except Exception:
            pass
```

Note for the implementer: the FPS label (computed in `set_frame`) now measures render cadence instead of raw arrival cadence — ≈13.3 when healthy, visibly lower when the GUI thread is overloaded. That droop is a truthful overload indicator; no code change needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ui_slowdown_guards.py -v`
Expected: all 7 PASS.

- [ ] **Step 5: Camera-safe suites still green, then commit**

Run: `python -m pytest tests/test_raster_pathmodel.py tests/test_zmq_v2_protocol.py -q`
Expected: all pass. Then:

```bash
cd /c/Users/radmo/labscript-suite/GUIs/rastering-slowdown-fix && git add ui.py tests/test_ui_slowdown_guards.py && git commit -m "fix(ui): coalesce camera frames drop-to-latest

new_frame was a direct queued connection into set_frame; whenever the
GUI thread fell behind the ~13.3 fps camera, 1.3 MB frame events piled
up in the Qt event queue without bound (memory + latency spiral).
Frames now land in an O(1) latest-frame slot; a 40 ms GUI-thread timer
renders the newest pending frame and skips stale ones.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Bound the log pane document

**Files:**
- Modify: `GUIs/rastering-slowdown-fix/ui.py:78` (immediately after `uic.loadUi(ui_path, self)`)

**Interfaces:**
- Consumes: `textEdit_2` (QTextEdit from `raster_gui.ui`, the `_log` sink at `ui.py:2447`).
- Produces: nothing new — `_log` behavior unchanged except oldest lines drop past 5000.

- [ ] **Step 1: Implement**

Insert immediately after `uic.loadUi(ui_path, self)`:

```python
        # Bound the log pane: it is append-only for the life of the process
        # (camera-error bursts route here), and an unbounded QTextDocument is
        # a slow memory sink on multi-day sessions. Oldest lines drop first.
        if hasattr(self, "textEdit_2"):
            self.textEdit_2.document().setMaximumBlockCount(5000)
```

(One-liner behind the same `hasattr` guard `_log` itself uses; no unit test — Qt's own behavior, nothing of ours to break. Verified in Task 5's live smoke.)

- [ ] **Step 2: Syntax check + suites green**

Run: `python -m py_compile ui.py && python -m pytest tests/test_raster_pathmodel.py tests/test_zmq_v2_protocol.py tests/test_ui_slowdown_guards.py -q`
Expected: compile OK, all tests pass.

- [ ] **Step 3: Commit**

```bash
cd /c/Users/radmo/labscript-suite/GUIs/rastering-slowdown-fix && git add ui.py && git commit -m "fix(ui): cap log pane at 5000 blocks

textEdit_2 was append-only and unbounded; camera-error bursts made it a
slow memory sink over multi-day sessions.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Verification, merge checkpoint, deploy

**Files:**
- Modify: `GUIs/rastering` (live worktree — merge only, at the user checkpoint)

**Interfaces:**
- Consumes: branch `fix/gui-slowdown-history-dedup` with Tasks 2-4 committed.
- Produces: fix live on `main`; operator restarts the GUI to deploy.

- [ ] **Step 1: Confirm the GUI is not running** (ui-importing tests + smoke need the camera free)

Run (PowerShell): `Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -match 'main_rastering' }`
Expected: empty. If not empty: STOP and coordinate with the operator; do not run the remaining steps.

- [ ] **Step 2: Full test pass in the worktree**

Run: `cd /c/Users/radmo/labscript-suite/GUIs/rastering-slowdown-fix && conda activate rastering && python -m pytest tests/test_raster_pathmodel.py tests/test_zmq_v2_protocol.py tests/test_ui_slowdown_guards.py -q`
Expected: all pass.

- [ ] **Step 3: Sim-mode smoke launch** (real camera, simulated motors — verified-safe headless pattern)

Run: `cd /c/Users/radmo/labscript-suite/GUIs/rastering-slowdown-fix && RASTER_SIMULATE=1 python main_rastering.py`, let it run ~30 s, then close the window.
Verify: window opens; live camera image updates; FPS label reads ≈13; check "Save position history", jog once in sim, confirm exactly one scatter point per distinct position (not one per second); log pane shows startup lines; clean exit, no traceback.

- [ ] **Step 4: CHECKPOINT — user confirmation before touching live `main`**

Present the diff summary (`git log --oneline main..fix/gui-slowdown-history-dedup` + `git diff main --stat`) and the smoke result to the user. Do not merge without an explicit go-ahead: `main` is what the operator runs between shots.

- [ ] **Step 5: Merge into live main**

```bash
cd /c/Users/radmo/labscript-suite/GUIs/rastering && git merge --no-ff fix/gui-slowdown-history-dedup -m "Merge fix/gui-slowdown-history-dedup: GUI slowdown root-cause fix + hardening

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Verify: `git show --stat HEAD` lists only `ui.py` and `tests/test_ui_slowdown_guards.py`. Do NOT push.

- [ ] **Step 6: Deploy + clean up worktree**

- Ask the operator to restart the rastering GUI (that IS the deploy; BLACS needs nothing — no protocol change).
- Remove the worktree (one mutation per call):

```bash
cd /c/Users/radmo/labscript-suite/GUIs/rastering && git worktree remove ../rastering-slowdown-fix
```

```bash
cd /c/Users/radmo/labscript-suite/GUIs/rastering && git branch -d fix/gui-slowdown-history-dedup
```

- [ ] **Step 7: Post-deploy observation note**

Next long session, confirm: FPS label stays ≈13 after hours of use; log pane no longer floods with `Frame grab failed` bursts; `position_history_*.csv` stays KB-sized. Log the outcome in `.claude/session-scratch.md`.

---

## Non-Goals (deliberate)

- **No scatter draw-cap/decimation** — dedup bounds `_history` by distinct positions (a raster path is at most a few thousand sites); a cap guards a case that can no longer occur. Add only if a future feature legitimately produces >50k *distinct* points.
- **No epsilon-based dedup** — idle polls return bit-identical floats on this hardware (CSV: 222 unique in 164k rows). The code comment names the ceiling.
- **No changes to the telemetry poll rate, controller, ZMQ protocol, or BLACS device** — the poll itself is healthy; only the UI's recording of it was wrong.
- **Old giant CSVs in `Logs/`** — left in place; they're inert on disk.
