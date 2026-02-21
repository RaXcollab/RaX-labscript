# RaX Lab — Labscript Suite

## Repository Structure

This is a **multi-repo workspace**. The parent directory (`labscript-suite/`) is the main user-facing git repo. Several subdirectories are **separate git repos** with their own remotes:

| Directory | Remote | Role |
|---|---|---|
| `.` (labscript-suite) | `github.com/RaXcollab/RaX-labscript` | **User-facing.** Tracks `userlib/` — custom devices, sequences, analysis, connection tables. |
| `blacs/` | `github.com/shafinulh/blacs` | **Backend.** BLACS runtime: state machine, device base classes, queue manager. |
| `labscript-devices/` | `github.com/shafinulh/labscript-devices` | **Backend.** Official device drivers (PrawnBlaster, NI_DAQmx, etc.) |
| `labscript-utils/` | `github.com/shafinulh/labscript-utils` | **Backend.** Shared utilities. |

The parent repo's `.gitignore` excludes the backend folders (`blacs/`, `labscript-devices/`, `labscript-utils/`, `app_saved_configs/`, `labconfig/`, `logs/`). **Commit to each repo separately.** Do not push without asking.

### Key Paths

```
userlib/
  user_devices/          ← Custom BLACS device classes (RemoteControl, NI_SCOPE, NuvuCamera, edge_counter)
  labscriptlib/          ← Experiment sequences, connection tables, globals
  analysislib/           ← Lyse analysis scripts
logs/
  BLACS.log              ← Main BLACS log
  BLACS_faulthandler.log ← C-level crash traces (segfaults)
labconfig/
  {COMPUTER_NAME}.ini    ← Per-machine config (apparatus name, paths, etc.)
```

## Python Environment

```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript
```

- Python 3.11, pyzmq=23.2.0 (do NOT upgrade pyzmq), numpy=1.26.4
- Backend repos are developer-installed: `pip install --no-build-isolation --no-deps -e blacs -e labscript-devices -e labscript-utils`

## Critical Conventions

### Qt Thread Safety in BLACS

**`@define_state` methods resume after `yield` in the mainloop BACKGROUND thread, not the Qt GUI thread.** This means:

- **USE `inmain()`** to call Qt widget methods (setValue, setText, show, hide, setEnabled, etc.)
- **DO NOT USE `with qtlock:`** for widget calls — it only pauses the Python-level event loop, does NOT marshal to the GUI thread. On Windows this causes access violations (segfaults).
- The upstream base class (`blacs/blacs/device_base_class.py:485-490`) explicitly uses `inmain()` with a comment explaining why.
- PUB-SUB daemon threads should use Qt signals (`pyqtSignal`) to communicate with the GUI thread, not direct widget calls.

### Worker Paths

Custom devices in `userlib/user_devices/` must use worker paths like:
```python
"user_devices.RemoteControl.blacs_workers.RemoteControlWorker"
```
NOT `"labscript_devices.RemoteControl..."` — that points to the wrong (or nonexistent) module.

### ExternalSoftware / RemoteControl Pattern

The `RemoteControl` device class (under `userlib/user_devices/RemoteControl/`) provides a template for interfacing BLACS with external programs (laser lock GUI, rastering GUI, etc.) via ZMQ:

- **REQ-REP** (synchronous): BLACS sends requests (PROGRAM_VALUE, CHECK_VALUE), external server responds. Used for setpoint control, manual programming, and buffered shot programming.
- **PUB-SUB** (asynchronous): External server publishes monitor values, BLACS subscribes. Used for real-time feedback (laser frequency, motor positions). ~300-500ms latency, fine for human monitoring.

Each device has 3 classes:
1. `labscript_devices.py` — Connection table API (`RemoteControl`, `RemoteAnalogOut`, `RemoteAnalogMonitor`)
2. `blacs_tabs.py` — BLACS GUI tab (`RemoteControlTab`)
3. `blacs_workers.py` — Worker process (`RemoteControlWorker`, `RemoteCommunication`)

### State Machine Event Ordering

Events queued by `@define_state` methods execute in FIFO order in the mainloop thread. The base class `DeviceTab.__init__` runs: `initialise_GUI()` → `restore_save_data()` → `initialise_workers()` → `program_device()`. Events queued during `initialise_workers` (like `connect_to_reqrep`) execute before `program_device`.

## Reference Documentation

- `Labscript-Confluence-2026-02-11.pdf` in repo root — Lab-specific Confluence docs covering installation, connection tables, ExternalSoftware communication, debugging notes.
- Official labscript docs: https://docs.labscriptsuite.org/
