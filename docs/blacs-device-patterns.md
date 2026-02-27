These patterns address friction points in the BLACS base class that affect any RemoteControl-pattern device with ordering constraints or non-spinbox UI. See `notes/2026-02-22_BigSky_tab_redesign.html` for the full writeup.

**Problem 1: `program_manual` sends ALL values, not deltas.** The base class calls `get_front_panel_values()` on every change, then sends the full dict to the worker. For devices where re-sending an unchanged value has side effects (e.g., BigSky rejects mode changes while lamps are active), this causes silent failures.

**Pattern: `_last_sent_values` delta tracking (worker-side)**
```python
def init(self):
    super().init()
    self._last_sent_values = {}

def check_remote_values(self):
    # ... get remote_values ...
    self._last_sent_values.update(remote_values)  # seed from remote state
    return remote_values

def program_manual(self, front_panel_values):
    for connection, value in front_panel_values.items():
        if self._last_sent_values.get(connection) == value:
            continue  # skip unchanged
        # ... send value ...
        self._last_sent_values[connection] = value
```

**Problem 2: `check_remote_values` poll races with user input.** The 5s periodic poll returns stale values and overwrites AO objects via `_update_ao_widgets`. With spinboxes this is a brief flicker; with toggle buttons the revert is very visible and can cause the reverted value to be programmed to hardware.

**Pattern: `_recently_changed` cooldown (tab-side)**
```python
self._recently_changed = {}  # {connection: monotonic_timestamp}

def _on_toggle_clicked(self, connection, value):
    self._recently_changed[connection] = time.monotonic()
    self._AO[connection].set_value(value, program=True)

def _update_ao_widgets(self, connection, value):
    if time.monotonic() - self._recently_changed.get(connection, 0) < 10:
        return  # skip — user changed this recently, poll hasn't caught up
    # ... update widget ...
```
Set the cooldown to 2x the poll interval (default 5s → 10s cooldown).

**Problem 3: `transition_to_buffered` uses safe ordering, `program_manual` does not.** If your device has command ordering constraints (e.g., must be in standby before changing mode), implement ordering in `program_manual` or the worker, not just in `transition_to_buffered`.

**Custom `initialise_GUI` pattern:** Call `create_analog_outputs()` for ALL channels (BLACS needs AO objects for save/restore and `program_device`). Create standard widgets only for continuous values. Binary controls → toggle buttons. Mode selectors → combo boxes. Command-only channels → hidden (no widget). Custom widgets call `AO.set_value(value, program=True)`.

**Problem 4: `_fetch_initial_values` blindly accepts remote zeros after GUI restart.** The base class fetches remote values on startup and updates the front panel unconditionally. If the remote GUI has no config persistence and restarts with zeroed values, BLACS silently overwrites its saved state (which may contain correct setpoints from the last session).

**Pattern: startup mismatch dialog (tab-side override)**
```python
@define_state(MODE_MANUAL, True)
def _fetch_initial_values(self):
    remote_values = yield (
        self.queue_work(self.primary_worker, 'check_remote_values')
    )
    # Compare remote_values vs self._AO[connection].value
    # If mismatch > threshold: show QMessageBox, let user choose
    # "Use saved" → self._mark_initial_fetch_done(); self.program_device()
    # "Accept remote" → inmain(self._update_ao_widgets, remote_values)
```
Implemented in `LaserLockTab`. Consider for any RemoteControl device where the remote GUI lacks config persistence.

---

## BLACS Saved-State Resilience

When the connection table changes (devices added/removed, parameters changed), BLACS handles stale saved state gracefully. `FrontPanelSettings.check_row()` silently excludes channels no longer in the connection table. **No need to delete the saved state h5 file** after connection table changes.

## State Machine Event Ordering

Events queued by `@define_state` methods execute in FIFO order in the mainloop thread. The base class `DeviceTab.__init__` runs: `initialise_GUI()` → `restore_save_data()` → `initialise_workers()` → `program_device()`. Events queued during `initialise_workers` (like `connect_to_reqrep`) execute before `program_device`.
