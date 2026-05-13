# HF_Locking — Gate Plot Updates on `chk_use`

**Date:** 2026-05-06
**Status:** Proposed
**Scope:** `GUIs/HF_Locking/display.py` only. `display_wide.py` / `main_wlm_wide.py` deletion is included as adjacent cleanup.

## Context

After reverting `_gui_timer_fast` to `Qt.CoarseTimer` on 2026-05-06 (see
`2026-05-05-hf-locking-rates-design.md` Follow-up), the GUI is responsive
again, but the per-frame work in `_refresh_gui_fast` still grows linearly
with channel count: every 33 ms, all 8 channels run
`ChannelControl.update_fast`, which performs deque purge + 2 ×
`pyqtgraph.setData` + `setXRange` + Y-autoscale. With the unthrottled
producer (worker @ 50 Hz, EcoQoS-off, ABOVE_NORMAL) contending the GIL,
this is a sustained pressure on the GUI thread. It was also the proximate
trigger for the failed PreciseTimer experiment.

The user observation: not every channel is meaningful at all times. The
`chk_use` checkbox already gates whether the WLM switcher includes a port
in its measurement cycle. If `chk_use` is unchecked, the channel produces
no fresh data — redrawing it 30× per second is pure waste.

## Decision

Two surgical edits to `display.py`, both in `class ChannelControl`.

### 1. Early return in `update_fast` when `chk_use` is off

```python
def update_fast(self, meas: dict):
    if not self.chk_use.isChecked():
        return
    # ... existing body unchanged
```

Skips deque purge, deque append, both `setData` calls, `setXRange`, and
the Y-autoscale loop. Single new branch at the top — no other code touched.

### 2. Clear deque + curves AND reset readouts to inactive state when user toggles `chk_use` off — extend `_on_switcher`

```python
def _on_switcher(self):
    if not self.chk_use.isChecked():
        # Auto-disable lock when channel is taken out of the cycle
        if self.lock_btn.isChecked():
            self.lock_btn.blockSignals(True)
            self.lock_btn.setChecked(False)
            self.lock_btn.blockSignals(False)
            self.request_lock.emit(self.port, False)
        # Clear plot buffers
        self.t.clear()
        self.f.clear()
        self.v.clear()
        self.curve_freq.setData([], [])
        self.curve_volt.setData([], [])
        # Reset readouts so a Use=off channel doesn't show a stale "Locked" badge
        self.lbl_exp.setText("Exp: --")
        self.bar_amp1.setValue(0)
        self.bar_amp2.setValue(0)
        self.status_label.setText(
            f"<b>{self.name}: <span style='color:#7f8c8d'>INACTIVE</span></b>"
        )
        # Invalidate guarded-update caches so re-enable triggers fresh setText / setYRange
        self._last_exp_text = None
        self._last_amp1 = -1
        self._last_amp2 = -1
        self._last_status_text = None
        self._prev_freq_yrange = None
        self._prev_volt_yrange = None
    self.request_switcher.emit(
        self.port, self.chk_use.isChecked(), self.chk_show.isChecked()
    )
```

Rationale (plot clear): when a channel is taken out of the cycle, leaving
the last plot frame frozen on screen looks like live data. Clearing makes
"no measurement" visually unambiguous, and prevents stale values from
lingering when Use is re-enabled.

Rationale (readout reset): `update_fast` (display.py:404-443) also writes
the exposure label, amplitude bars, and color-coded status text. The
early return in §1 silently freezes those, leaving a Use=off channel
showing a green "Locked" badge with its last frequency — misleading. The
explicit reset writes a neutral "INACTIVE" state. Gray (`#7f8c8d`)
matches the existing **NO SIGNAL** styling at display.py:431 — same
vocabulary for "quiescent state."

Rationale (auto-disable lock): clicking the lock button when the channel
is later toggled off would otherwise leave the channel "armed" — the
`SetPIDSetting(cmiDeviationChannel, ...)` assignment persists in
`SharedExperimentState.lock_enabled` and the WLM-side state, so re-enabling
Use would silently re-engage the lock without a user action. By explicitly
un-arming on Use→off (with `blockSignals` mirroring the established
pattern at `update_slow` / display.py:483), we keep the lock state
co-signed with the Use state. The `request_lock.emit(self.port, False)`
goes through the same worker path as a user click on the lock button
(`handle_lock_toggle` at workers.py:411), which issues
`set_channel_assignment(port, False)` to the DLL and updates
`SharedExperimentState`.

Cache invalidation (`_last_*` → None / -1, `_prev_*_yrange` → None) is
required because each readout has a guarded write (e.g.
`if exp_text != self._last_exp_text` or
`if (ylo, yhi, step) != self._prev_freq_yrange`). After re-enabling Use,
the next `update_fast` tick computes new values; if the cache still matches
the pre-toggle value, the write would be skipped and the label / axis range
would stay frozen. Setting caches to sentinel values guarantees the first
comparison fires. The `_prev_*_yrange` invalidation is defensive but
intentional — the user wants the Y-axis range to be recomputed on re-enable
so the axis tracks fresh data correctly.

`_on_switcher` is wired to `chk_use.clicked` (display.py:161), which fires
*only* on user clicks. Programmatic `setChecked()` in `set_status`
(display.py:472) is wrapped in `blockSignals(True)` / `blockSignals(False)`
— so config-restore loading Use=False on startup will not trigger a
redundant clear of an already-empty buffer or a redundant reset of
already-default labels.

### 3. Clear `_last_good_freq[port]` in worker when `use=False` — fixes stale BLACS broadcast

Added 2026-05-12 after hardware verification surfaced a real BLACS-side
bug. Worker side, [GUIs/HF_Locking/workers.py:379](GUIs/HF_Locking/workers.py#L379)
`handle_switcher_write`:

```python
def handle_switcher_write(self, port: int, use: bool, show: bool):
    self.wlm.set_switcher_signal(port, int(use), int(show))
    # Drop stale cached frequency when channel leaves the switcher cycle, so
    # subsequent polls (HARD_INVALID for disabled ports) yield freq_display=None
    # and ZMQ broadcasts a clean 0.0 sentinel instead of the pre-toggle value.
    if not use:
        self._last_good_freq[port] = None
    self.log_message.emit(...)
    # ... existing readback unchanged ...
```

**Bug fixed:** `WavemeterWorker._poll_fast` polls all 8 ports
unconditionally every 20 ms. When a port is excluded from the switcher
cycle (Use=False), the DLL returns a HARD_INVALID sentinel (e.g.
`ErrNotAvailable=-6`). `_normalize_frequency`
([workers.py:226-227](GUIs/HF_Locking/workers.py#L226-L227)) treats
HARD_INVALID as `valid=False` *but sets
`freq_display=last_good`* if `last_good` is non-None.
`ZMQPubWorker.run` ([workers.py:489](GUIs/HF_Locking/workers.py#L489))
then broadcasts the stale `last_good` as if live, at 10 Hz, indefinitely:
a channel locked at 348.666 THz and then Use-toggled off keeps publishing
`"{port} 348.666..."` to BLACS forever, even though the WLM is no longer
measuring that port.

**Fix mechanism:** clearing `_last_good_freq[port]` to None when the
worker handles the `use=False` switcher write means the next poll, finding
no `last_good`, leaves `freq_display=None` in the measurement packet. The
ZMQ PUB worker then emits `"{port} 0.0"` (per its existing `0.0 if f is
None else f` formatter) — a clean sentinel that BLACS-side
`RemoteAnalogMonitor` can recognize. No worker-side polling change required.

**Note on voltage:** there is no analogous `_last_good_volt` recycling in
the worker — voltage is read fresh per poll. Disabled ports may still
broadcast whatever the DLL returns for voltage on an unused port; this is
filed as a follow-up empirical bench test
([2026-05-12-hf-locking-followups.md](2026-05-12-hf-locking-followups.md)
item 3).

## Why not gate just the plot block?

A simpler-seeming alternative is to leave `update_fast` running
unconditionally and wrap *only* the plot-rendering portion in
`if self.chk_use.isChecked():`. Then the existing "NO SIGNAL" branch
(display.py:430-432) would naturally fire for unused channels and the
labels would self-quiesce — no `_on_switcher` reset needed.

**This does not work.** The worker's `_normalize_frequency`
([workers.py:212-214](GUIs/HF_Locking/workers.py#L212-L214)) deliberately
recycles `last_good` with `valid=True` when the WLM returns
`InfNothingChanged`:

```
InfNothingChanged -> treat as "no new sample":
  if last_good exists: valid=True, raw=last_good, plot=last_good, display=last_good
  else: valid=False
```

The recycling exists to avoid `-7` spikes during normal switcher cycle
gaps and is load-bearing for the lock-detection path. So when Use=off,
the worker keeps reporting `valid=True` with the cached frequency, the
status block computes "Locked"/"Unlocked" against that cached value, and
the existing "NO SIGNAL" branch never fires. Disturbing the worker's
recycling logic to signal Use=off via `valid=False` would corrupt the
lock-wait machinery.

The right boundary is the GUI layer: when the user removes a channel
from the cycle, the *GUI* declares it inactive locally, independent of
what the worker reports.

**Note on prior behavior.** Pre-edit, Use=off channels already showed
frozen labels (the cache-compare guards at lines 407, 415, 441 suppress
redundant `setText` calls when the recycled value doesn't change). The
early-return in §1 doesn't make this worse — it just makes the *plot*
freeze too. The §2 readout reset fixes a pre-existing UX bug while we're
in this code path.

## Concurrency / ordering

Both `_on_switcher` (click handler) and `_refresh_gui_fast` (GUI timer
slot) run on the Qt main thread, serialized by the event loop. No race
between buffer clear and the next frame: either the click handler runs
first (clear, then early-return on the next refresh) or the refresh runs
first (one more painted frame, then the clear). Either order is correct.

The worker QThread writes to `SharedExperimentState` independently, but
the GUI only reads via `get_all_measurements()` snapshots — the worker's
state is never touched by `_on_switcher`. Toggling Use off does NOT stop
the worker from continuing to poll the (now-removed-from-cycle) port —
the WLM simply returns `InfNothingChanged` for it, which is already
handled.

## Out of scope

- **`chk_show`** — left as a pure visibility toggle. No performance
  gating in this change. Could be added as a second early-return condition
  later if it proves useful.
- **Per-frame change detection** ("only `setData` on channels whose data
  changed since last frame") — superseded by the `chk_use` gate, which is
  user-driven and far simpler.
- **PreciseTimer reconsideration** — even with reduced per-frame work,
  the Windows multimedia-timer message-pump issue is independent of work
  cost. Rule from 2026-05-06 stands: CoarseTimer for any QTimer driving
  work on the Qt main thread. See
  `feedback_qt-precisetimer-gui-thread-windows.md`.

## Files Changed

- `GUIs/HF_Locking/display.py` — 2 edits in `class ChannelControl`: early
  return in `update_fast` (§1), and conditional auto-lock-disable +
  plot-clear + readout reset + 6-cache invalidation in `_on_switcher`
  (§2). Net add ≈29 lines.
- `GUIs/HF_Locking/workers.py` — 1 edit in `WavemeterWorker.handle_switcher_write`:
  clear `_last_good_freq[port]` when `use=False` (§3). Net add ≈5 lines
  (incl. 3-line comment block).
- `GUIs/HF_Locking/CLAUDE.md` — already updated this session: removed
  `display_wide.py` and `main_wlm_wide.py` rows from the file-map and the
  matching "Known TODOs in Code" entry.
- `GUIs/HF_Locking/display_wide.py` — **deleted** this session
  (incomplete wide-layout variant, no imports).
- `GUIs/HF_Locking/main_wlm_wide.py` — **deleted** this session
  (incomplete wide-layout variant, no imports).

## Verification

1. **Baseline launch**: relaunch GUI, all 8 channels Use=on. Confirm
   plots refresh smoothly at 30 Hz (visually identical to current
   behavior).
2. **Single-channel toggle off — plot clears**: uncheck Use on one
   channel. Both `curve_freq` and `curve_volt` clear immediately; plot
   area becomes empty.
3. **Single-channel toggle off — readouts go inactive AND lock disables**:
   on the same click: exposure label → "Exp: --", both amplitude bars
   → 0, status label → gray "<b>{name}: INACTIVE</b>". Critically: a
   previously locked channel (showing green "Locked") must NOT keep
   showing "Locked" after the toggle. Additionally: if `lock_btn` was
   checked, it visibly unchecks (and the worker receives
   `request_lock(port, False)` → DLL deassignment).
4. **Toggle back on**: re-check Use. Plot starts populating from current
   time forward — no stale points from before the toggle-off. After the
   next worker poll (≤200 ms), the status label updates to a fresh
   "Locked"/"Unlocked"/"NO SIGNAL" — not stuck on "INACTIVE". The
   exposure label and amp bars also refresh.
5. **`chk_show` toggle independence**: with Use=on on a channel, click
   Show off then on then off. Plot keeps showing live data; status
   label keeps showing the live state. (The shared `_on_switcher` slot
   fires for both checkboxes, but the `if not chk_use.isChecked()` guard
   means none of the inactive-state code runs while Use is on.)
6. **Config persistence**: relaunch with a Use=False channel persisted in
   `pid_config.json`. Loads with empty plot AND default labels (the
   `set_status` blockSignals path means `_on_switcher` does not fire on
   restore, so the constructor's default labels are what the user sees —
   no "INACTIVE" text from a clear that never ran). No clear-flash, no
   error.
7. **Throughput**: with 4 channels Use=off and 4 Use=on, watch for
   visible smoothness improvement on the active 4 (should feel less
   choppy under contention). Optional: enable
   `diagnostics.ENABLED=True`, confirm `WARN_GUI_UPDATE_MS` (20 ms
   threshold) fires less frequently.
8. **BLACS broadcast cleared for Use=off ports** (§3 worker fix): with
   BLACS running, lock a channel at a known frequency (e.g. 348.666 THz);
   toggle Use=off on that channel; watch the BLACS-side monitor for that
   port — should drop to `0.0` (clean sentinel) within ≤200 ms, NOT keep
   showing the pre-toggle frequency. Then re-enable and confirm BLACS
   sees live data again on the next worker poll.
9. **No regression**: BLACS-side `LaserLockDevice` still receives ZMQ
   updates for enabled channels; setpoint writes via REQ-REP work for
   all enabled channels.

## Expected impact

8 channels → typically 2-4 in use → 50-75% reduction in pyqtgraph
`setData` work per 33 ms frame on the GUI main thread. Restores headroom
against the unthrottled (EcoQoS-off, ABOVE_NORMAL) worker thread, and
removes the per-frame cost pressure that prompted the failed PreciseTimer
experiment.

## Related

- Code: `GUIs/HF_Locking/display.py` (`class ChannelControl`),
  `main_wlm.py` (`_refresh_gui_fast`)
- Rate inventory: `docs/hf-locking-rates.md`
- Prior design: `docs/superpowers/specs/2026-05-05-hf-locking-rates-design.md`
- Auto-memory: `feedback_qt-precisetimer-gui-thread-windows.md`
