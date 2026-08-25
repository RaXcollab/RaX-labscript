# BLACS State Machine — Canonical Reference (RaXcollab fork)

**Status:** Current fork reference
**Last reviewed:** 2026-08-21

This document describes BLACS scheduling, per-shot lifecycle changes, and RemoteControl integration.

Use the fork code when it differs from official labscript documentation.

## Process model — 3-tier zprocess tree

```
 blacs.__main__  (GUI process — Qt main thread)
         │
         ├──  Per-device Tab object  (lives in the GUI process)
         │        │
         │        └──  Per-tab mainloop thread (daemon)
         │                 └── pulls from StateQueue, dispatches to worker
         │
         └──  Per-device Worker  (separate OS process via zprocess)
                  └── holds hardware libraries (PyDAQmx, niscope, pyserial, ...)
```

- **Tab↔Worker queues** are pickled `to_worker` / `from_worker` zprocess queues.
- **Other GUI-process threads**: `QueueManager.manage` (shot queue), `AnalysisSubmission.mainloop` (lyse submission), ZMQ `ExperimentServer` (receives shots from RunManager).
- **Transport spine**: `labscript_utils.ls_zprocess` (CurveZMQ over shared secret, pyzmq=23.2.0 pinned).
- **Shot h5 file is the contract** between RunManager ↔ BLACS ↔ lyse ↔ runviewer. Path-agnostic (`shared_drive.path_to_agnostic`) so machines with different mount letters interoperate.

## MODE bitmask

Defined in `blacs/blacs/tab_base_classes.py:64`:

| Flag | Value | Meaning | Origin |
|---|---|---|---|
| `MODE_MANUAL` | 1 | Idle; user-driven | stock |
| `MODE_TRANSITION_TO_BUFFERED` | 2 | T2B — preparing to run | stock |
| `MODE_TRANSITION_TO_MANUAL` | 4 | T2M — tearing down to idle | stock |
| `MODE_BUFFERED` | 8 | Shot executing | stock |
| `MODE_TRANSITION_TO_POST_EXP` | **16** | T2POST | **fork** |
| `MODE_POST_EXP` | **32** | Between-shot idle in queue | **fork** |

OR-able. `allowed_modes` on `@define_state` is `1..63` (any combination).

## `@define_state` mechanics

```python
@define_state(allowed_modes=MODE_MANUAL|MODE_POST_EXP, queue_state_indefinitely=True, delete_stale_states=False)
def my_callback(self, ...):
    # body runs in the MAINLOOP background thread, not the Qt GUI thread
    ...
    yield (worker_task, check_main_first)   # or yield ([t1, t2, ...], check_main_first)
    # resumes here after worker(s) complete
```

- Calling a `@define_state` method does NOT execute it — it enqueues `[fn, [args, kwargs]]` onto the StateQueue.
- The mainloop pulls FIFO within priority and runs the body.
- `yield (worker_task, check_main_first)` dispatches work to the worker process and suspends. The mainloop later calls `generator.send(result)` to resume.
- **`yield ([task_1, task_2, ...], check_main_first)`** is the fork's multi-worker API — fan out work to multiple workers in parallel, resume after all complete. Old single-task `yield self.queue_work(...)` is back-compat via the `old_worker_flow` branch.

## StateQueue + garbage collection

- `insort` by `[priority, monotonic_unique_id, ...]` — matches `(priority, next(itertools.count()), obj)` pattern (see [[reference_priorityqueue-monotonic-tiebreaker]]).
- **`delete_stale_states=True`** collapses consecutive identical statefuncs to the latest. How spammed `program_device` calls coalesce.
- **`queue_state_indefinitely=False`** states are **discarded** if mode mismatches when reached. This is the stale-event GC: e.g. `abort_transition_to_buffered` queued from MANUAL but reached after T2B → discarded.
- `priority=-1` jumps the queue (`_initialise_worker`, `create_worker`, `_quit`, `close_tab`).
- `@define_state(..., delete_stale_states=True)` and `queue_state_indefinitely=True` are the canonical settings for periodic polls (program_device, check_remote_values).

## Per-shot lifecycle — fork-specific

**Queued shots** (3+ shots in BLACS queue):

```
Shot 1:  transition_to_buffered → start_run → post_experiment
Shot 2:  transition_to_buffered → start_run → post_experiment   ← NO transition_to_manual
Shot 3:  transition_to_buffered → start_run → post_experiment
...
Last:    transition_to_manual                                  ← only at queue-end / abort / pause
```

**Single shot from MANUAL**:

```
MANUAL → T2B → BUFFERED → start_run → POST_EXP → MANUAL
```

**Key rule** (load-bearing): per-shot device teardown belongs in `post_experiment`, NOT `transition_to_manual`. The latter only runs at queue-end. See [[reference_post-experiment-vs-transition-to-manual]].

## `post_experiment(notify_queue, program, skip_manual)` worker hook

- Runs between BUFFERED and the next state (next T2B if queued, or T2M if queue-ending).
- `skip_manual=True` is passed when more shots are queued. Devices use this to defer expensive widget syncs.
- **Back-compat fallback**: worker classes that don't implement `post_experiment` trigger a ~80 ms first-shot probe per shot. Implement the hook to skip the probe.
- `@define_state(allowed_modes=...)` must include `MODE_POST_EXP` if the callback should fire between queued shots (e.g. PUB-SUB monitor polls, BigSky auto-rearm checks). Omitting POST_EXP silently disables the callback in the queued-shot window — a load-bearing trap.

## `QueueManager.manage()` flow

- Wait on `current_queue` (treeview row 0) → read `devices` / `start_order` / `stop_order` from h5.
- T2B grouped by `start_order` (`defaultdict(set)`, ascending `min()`), polling `current_queue` until all devices report success or `timeout_limit=300s`.
- `master_pseudoclock.start_run(experiment_finished_queue)`.
- Poll for done / abort / restart / tab-error.
- T2M grouped by `stop_order`. `tab.post_experiment(current_queue, skip_manual=queued_experiments)`.
- Store front panel + `data` group + `run time` into h5; submit to analysis.
- On abort: pause queue, prepend path, `abort_buffered` all devices, **recreate `current_queue`** to drop stale device replies (key stale-event defense).

## `check_remote_values` polling

- **Base default**: `device_base_class.py:67` registers `statemachine_timeout_add(30000, check_remote_values)` — every 30 s.
- **`RemoteControlTab` override**: `userlib/user_devices/RemoteControl/blacs_tabs.py:325` calls `statemachine_timeout_add(5000, ...)` — every 5 s for the lab's userlib RemoteControl devices.
- **During `wait_for_lock`** (line 382): `statemachine_timeout_add(500, ...)` — back off to 500 ms for tighter convergence checking.
- Steady-state after the lock-wait window: back to 5000 ms (line 384).
- Race vs user input: the poll can overwrite AO widgets between `check_remote_values` and a user spinbox change → `_recently_changed` cooldown pattern (10 s) suppresses poll updates for recently-changed channels.

## `program_device` / `program_manual`

- `program_device` is `@define_state(MODE_MANUAL, True, delete_stale_states=True)`. Spam coalesces.
- Sends **ALL** values to workers (not deltas). Worker is responsible for delta-tracking via `_last_sent_values` if hardware has ordering constraints (e.g. BigSky mode-change-requires-standby).
- After `post_experiment` clears tasks (`self.DO_task = None`), `program_manual` silently no-ops for DO writes. Use `_ensure_manual_DO_task()` to create a temporary DO-only task when needed between queued shots.

## Qt thread safety (load-bearing — memorize)

- `@define_state` methods resume after `yield` in the **MAINLOOP BACKGROUND THREAD**, NOT the Qt GUI thread.
- **USE `inmain()` / `@inmain_decorator(True)`** for any widget call (setValue, setText, show, hide, setEnabled, addItem, etc.).
- **DO NOT USE `with qtlock:`** — it pauses the event loop but does not marshal calls to the GUI thread.
- PUB-SUB daemon threads → use `pyqtSignal` to bridge to GUI thread (`_PubSubSignalBridge` pattern).

## Stale-event / race hazards

- `queue_state_indefinitely=False` states discarded if mode mismatches at execution time. E.g. `abort_transition_to_buffered` is `queue_state_indefinitely=False`; if the queue manager already moved to MANUAL by the time it reaches the head, it gets dropped.
- `delete_stale_states=True` only collapses **consecutive** identical statefuncs. A `program_device` then `program_manual` then `program_device` will execute all three.
- `check_remote_values` 30 s poll (base) vs user input: handled via `_recently_changed` cooldown.
- `program_manual` sends ALL values, not deltas — devices with mode-ordering constraints must delta-track in the worker (BigSky pattern).
- `post_experiment` back-compat probe imports the worker module in the GUI process (string-path case) — side-effect risk if worker module has import-time behavior.
- **`transition_to_manual` is `queue_state_indefinitely=False`**: missing T2M between queued shots is by design — per-shot teardown MUST be in `post_experiment`.

## Custom RemoteControl plug-in points

- `userlib/user_devices/RemoteControl/` is the active runtime base. The labscript-devices copy is dead code — see [[reference_two-remotecontrol-trees]].
- `RemoteControlTab` subclasses `DeviceTab`: overrides `initialise_GUI` (custom widgets calling `AO.set_value(v, program=True)`), `initialise_workers` (worker path string `"user_devices.RemoteControl.blacs_workers.RemoteControlWorker"`), `supports_remote_value_check(True)`.
- Worker REQ-REP `CHECK_VALUE` ↔ `check_remote_values`; PUB-SUB monitor cache shared via `init_kwargs`; per-shot snapshots written in `transition_to_buffered` (`initial_monitor_values`) / `post_experiment` (`final_monitor_values`) to `/data/{device}/monitor_values/...` (see `docs/shot-h5-layout.md`).
- Override `program_manual` (delta-track), `transition_to_buffered` (safe ordering), `post_experiment` (per-shot cleanup, NOT `transition_to_manual`).

## NI shared-worker caveat

`NI_DAQmxOutputWorker` is the single worker class used by **all** NI devices (NI_PXIe_6361, NI_PXIe_6535, etc.). Changes to its `transition_to_buffered`, `post_experiment`, or `transition_to_manual` affect every NI device. The latched-lines mechanism inside it (see `docs/blacs-device-patterns.md` "Latched Digital Output Pattern" and [[reference_ni-daqmx-latched-lines-three-layer-restore]]) is gated on `if self._latched_lines:` so devices without latched lines pay no cost.

## See also

- `docs/blacs-device-patterns.md` — device-side patterns (latched lines, BigSky keep-warm, saved-state resilience, NI_DAQmxOutputWorker lifecycle).
- `docs/remotecontrol-zmq-protocol-v2.md` — external GUI ZMQ protocol.
- `docs/external-guis-architecture.md` — three-GUI overview.
- `docs/shot-h5-layout.md` — h5 file structure.
