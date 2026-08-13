# Ponytail Audit — labscript-suite workspace (2026-08-12)

Repo-wide over-engineering audit. **Report only — nothing has been applied.**
Check a box to approve a cut; strike or annotate to reject.

**Scope:** parent repo tracked files (userlib, tests/, .claude tooling, root misc), the three
registered GUI repos (HF_Locking, rastering, BigSkyControl) + stale sibling workspaces, and the
lab's custom delta in the backend forks (`diff official/master...HEAD` in blacs,
labscript-devices, labscript-utils). Not audited: non-registered GUI dirs (LakeshoreGUI, MKS,
quadmag, Thermocouples, LabMonitoring, Microcontrollers), upstream backend code we never touched.

**Method:** 9 audit passes (5 spawned auditors, 2 duplicate relaunches used as corroboration,
2 peer-session audits) → 7 domain vetting passes (blacs-expert ×2, lyse-analysis, amo-expert,
ablation-tech, BigSky laser-controller, HF_Locking). Every finding below carries the vet verdict.

## Headline

| Bucket | Amount |
|---|---|
| Confirmed cuttable now | **~11,000 lines** + 6 stale worktrees (~22 MB) + 1 tracked binary |
| Conditional (needs sign-off / rule edit / paired change) | ~4,300 lines |
| Claimed by audits but **REJECTED** by domain vetting | ~1,600 lines |
| Dependencies removable | 0 |

---

## Tier 1 — Confirmed cuts (ranked biggest first)

### Whole trees / files

- [ ] `delete:` **GUIs/rastering/Old Code/** — zero references anywhere (incl. `lyman_calibration_data.json` inside it); last commit "Backup" 2026-02-03; git history preserves it. (~5,872 lines + 3.2 MB PNGs)
- [ ] `delete:` **labscript-devices/labscript_devices/RemoteControl/** — dead twin of userlib's live tree; register_classes.py 100% commented so BLACS never loads it; deleting also removes a registry-shadowing trap. Update the prose ref in `.claude/agents/device-builder.md:38` same commit. (~1,119)
- [ ] `delete:` **userlib/labscriptlib/main_experiment_control/** — superseded by Main_Experiment/, self-referential imports only, untouched since 2025-02. NI_PXIe_6739 concern checked: imports *from* labscript-devices, orphans nothing. (~757)
- [ ] `delete:` **Jupyter notebooks/_build_scan_notebooks.py + _build_explorer.py** — both already broken (source notebook moved to `archive/` → FileNotFoundError); their outputs exist and have been hand-edited since (re-running would destroy operator edits). (~444)
- [ ] `delete:` **6 stale GUIs workspaces** — merged-and-clean worktrees `rastering-hull-reach`, `rastering-open-items`, `rastering-zmq-v2`, `rastering-fix-fresh-coord`, `HF_Locking-zmq-v2` (tips verified ancestors of main; only untracked CLAUDE.md scaffolding inside) + empty dir `rastering-stepping` (not a worktree — plain rmdir). **KEEP `rastering-atomic-xy`** — 1 commit ahead, unmerged. (~22 MB, 289 files)
- [ ] `delete:` **GUIs/HF_Locking/diagnostics.py** — its hooks say "called from patched workers/controller"; no such call sites ever existed (single commit 92f0cc4, never wired). Drop the two HF CLAUDE.md mentions same commit. (~183)
- [ ] `delete:` **userlib/labscriptlib/example_apparatus/** — upstream boilerplate; only ref is the never-loaded `labconfig/example.ini` template. (~166)
- [ ] `delete:` **analysislib/Main_Experiment/analysis_old.py** — absent from lyse.ini registry (the authority), superseded by analysis.py. (~164)
- [ ] `delete:` **.claude/_compare_rastering_sessions.py** — one-off forensic script, two hard-coded session UUIDs. (~120)
- [ ] `delete:` tracked binary **userlib/analysislib/anaconda_projects/db/project_filebrowser.db** — Navigator-generated cache; delete + gitignore. (32 KB)
- [ ] `delete:` **userlib/analysislib/common/** + **userlib/labscriptlib/common/** — empty packages, zero importers. (2 dirs)
- [ ] `delete:` stray unimportable **`userlib/user_devices/"__init__ .py"`** (space in filename) + banner-only NI_SCOPE `__init__.py` content. (~11)

### userlib/user_devices + external_gui_lib

- [ ] `shrink:` 35 nc_camera methods repeating try/raise-NuvuException/errorHandling → one `_call(self, fn, *args)`. [NuvuCamera/Nuvu_sdk/nc_camera.py] (~150)
- [ ] `delete:` Nuvu_sdk dead surface: unreferenced wrappers (`saveImage`, `setRawEmGain`, `getControllerTemp`, `camIsAcquring`, `purgeBuffer`, `updateCam`), 9 never-called ctypes prototypes in NC_api.py, module-level `matplotlib.pyplot` + `__main__` demo in worker-imported file, `disconnect_if_error` no-op decorator + 15 applications (keep `disconnect_if_error_real`; update docs/known-latent-issues.md), `get_image64`/`millisecond_to_fps` (CAVEAT: `__real_fps` touches a live exposure setter — edit carefully), unused defines, `macAdress` branch. (~170)
- [ ] `delete:` commented-out predecessor classes above live code. [NI_SCOPE/labscript_devices.py, edge_counter/labscript_devices.py, edge_counter/blacs_tabs.py] (~129)
- [ ] `shrink:` 5 byte-identical `tests/conftest.py` sys.path bootstraps + inline copy in test_zmq_v2.py → one `userlib/conftest.py`. CAVEAT: holds because pre-push runs pytest from repo root; running pytest from inside a device tests/ dir won't pick it up. (~90)
- [ ] `delete:` `MultiStaticOutputValue` — "Under development", zero references incl. all 5 connection tables and GUIs. [RemoteControl/labscript_devices.py] (~83)
- [ ] `delete:` **dead monitor-read surface, one commit**: worker `check_status`, tab `status_monitor` (never registered with statemachine_timeout_add anywhere) + `_update_monitor_widgets`, base `check_all_remote_values` (BigSky's own override stays), tab `_pubsub_monitor_cache` (write-only; worker uses its own `_pubsub_cache` across the process boundary) + repoint `test_tab_registry.py` at `_extra_topics`/`_subscriber_thread`. **Must update the 4 docs naming these**: remotecontrol-zmq-protocol-v2.md:522,546, shot-h5-layout.md, frame-explicit-coords-design.md:175,217-220, RemoteControl/README.md:59. Note: the AO-setpoint REQ-REP poll (`check_remote_values`, 5 s / 500 ms) is **live** — only the monitor-value poll is dead. (~80)
- [ ] `delete:` BigSkyHub worker `enter_warmup`/`exit_warmup` — no caller incl. `queue_work` string dispatch; live paths are `_restore_warmup`/`_arm_laser`. (~48)
- [ ] `shrink:` BigSky tab: combo-enable predicate ×3 → `_combo_enabled(prefix)`; 4 stylesheet copies → `_btn_style(bg, fg)`; delete never-read `_BINARY_OUTPUTS`/`_MODE_OUTPUTS`/`_COMMAND_OUTPUTS`. [BigSkyHub/blacs_tabs.py] (~48)
- [ ] `delete:` pure-delegation/dead overrides: `RemoteControl.add_device`, `Nuvu_wrapper_error.__init__`, `NuvuCamera._decode_image_data`, `NI_SCOPE.generate_code`, `global NuvuCam`, unused imports (rich_print/json ×2). **NI_SCOPE abort methods: use the aliasing form** `abort_buffered = abort_transition_to_buffered = abort` (class attrs keep the by-name entry points BLACS calls — outright deletion was vetoed). (~30)
- [ ] `delete:` zmq_v2 safe subset only: `Transport` Protocol class (type-hint only), `client_matches_advertised` + its 3 tests, unused `abstractmethod` import, `v1_refused_reply` one-caller wrapper, `__main__` subprocess pytest self-runner. **PING handler and RequestIdCounter stay** (documented v2 surface + production caller). (~45)
- [ ] `shrink:` LaserLock tab `_pairs` 4-tuples → `{conn_id: display_name}`; edge_counter manual h5 group loop + RemoteControl try/except-KeyError → `require_group`. (~18)

### GUIs/rastering (code)

- [ ] `delete:` ~46 dead `hasattr(self, "<widget>")` guards — every named widget exists in raster_gui.ui (ships as a pair with ui.py on every branch; verified zero widget-name drift across all sibling worktrees). **Keep the 4 in `_update_step_mode_ui`** (load-bearing for the SimpleNamespace stub tests) unless stubs are extended. [ui.py] (~41)
- [ ] `stdlib:` 11 `try/except Exception: pass` → `contextlib.suppress(Exception)` (add the import — ui.py has none). [ui.py] (~20)
- [ ] `delete:` rastering controller dead code: `cancel_calibration`, `request_stop` (Stop button uses `stop_raster`), `segments_from_points`, `list_device_serials` — all verified against @handler routes, getattr dispatch, and userlib. (~45)
- [ ] `delete:` `build_controller()` manual fallback — `create_controller_from_config` unconditionally defined, branch unreachable. [main_rastering.py] (~34)
- [ ] `shrink:` `MotorResult(...)` ×25, 23 repeating cmd_id/source/tag → `cmd.result(ok, message="", **kw)` dataclass helper. [raster_controller.py] (~25)
- [ ] `shrink:` duplicated k_to_index+blockSignals dock-sync block → `_sync_display_widgets()`; `_move_reply(res, request_id)` for the twice-repeated reply block; `_set_flip(axis, checked)`; nearest-point scan → `min(range(len(pts)), key=…)`; `_apply_image_scale` wrapper inline; `_user_home_both` → lambda (CAVEAT: docstring is the atomic-xy invariant — move it to the connect site; expect merge churn with that worktree); name==key pairs; unused `typing.Optional`. [ui.py, camera_settings_dock.py] (~45)
- [ ] `delete:` unreachable .ui fallbacks: `raster_continuous_checkbox`/`raster_step_button` creation, `_auto_layout is None` branch (retires a prior `# ponytail:` marker), flip_x/flip_y legacy aliases; five `disconnect()` guards in `_install_raster_mode_controls` (exactly one caller). [ui.py] (~29)
- [ ] `yagni:` five pure pass-through signals in camera dock → connect child widgets directly (keep `rotation_changed`, it maps index→k); dead `RasterDefaults` fields x_step/y_step/spiral_* **plus unflagged `spiral_step`**; the 7 config aliases (never referenced by name — also delete the provably-dead `_get("SERIAL_X")`-style fallback args at raster_controller.py:2678-2714). (~30)

### GUIs/BigSkyControl

- [ ] `delete:` legacy v1 `"rejected:"` string-sniff net — provably dead: the only ERROR producers are "unknown command"/"GUI exception"; every rejection path returns structured REJECTED. (Re-verify if the mixin-split branch ever lands.) [HugeSkyController.pyw:180] (~23)
- [ ] `shrink:` `_prepMode(target)` for the identical startWarmup/startLaser prologue (`warmupActive` stays in caller). (~12)
- [ ] `shrink:` `updateAllStatusIndicators` three uniform label/color/button blocks → table+loop. **The interlock chain below (:720-750) stays imperative and untouched.** (~16)
- [ ] `shrink:` keep `self.btnContainer` from `__init__` instead of `layout.itemAtPosition(...)` — also fixes a real zero-lasers-at-start widget-grab bug. (~4)
- [ ] `delete:` misc confirmed: commented slider setValue lines (widgets don't exist in .ui), `>lpm` parser unified on `_TRAILING_INT_RE`, unused imports (concurrent.futures/QtCore/QtGui; json/QAction/QPixmap/pyqtSlot), write-only `proposedEnergy`, duplicated hysteresis docstring. (~18)

### GUIs/HF_Locking (cold-path batch — rank first per vetter; zero DLL-semantics change)

- [ ] `delete:` `verbose` blocks + StatusString ladder (False forever), `get_frequency` (zero callers incl. autospec tests), `get_all_status` (dead sibling of live `get_all_measurements`). [wlm_utils.py, workers.py] (~46)
- [ ] `shrink:` 4 registry loops in `read_live_state` → bound-method table; `get_deviation_bounds`/`set_channel_assignment`/`get_channel_assignment` → the existing wrappers (byte-equivalent ctypes); `Version_*` attrs → locals. [wlm_utils.py, config.py] (~45)
- [ ] `shrink:` `_target_screen()` helper for the duplicated QScreen loop; store `(cb, saved)` at checkbox build; delete `FREQ_PAD_FRAC`; delete stale "display_wide" comment (numpy import itself is hot-path, stays). [main_wlm.py, display.py] (~12)

### Backend fork deltas (blacs / labscript-devices / labscript-utils)

- [ ] `delete:` `PlotWindowTest` + `AnalogInputTest` demo harnesses + `__main__` blocks + their orphan imports (`time`, `sys`, the AnalogInputTest-only numpy — InputPlotWindow's numpy stays). [labscript-utils/qtwidgets/] (~119)
- [ ] `delete:` `_update_state_label` husk (body pass, all call sites commented). [blacs/tab_base_classes.py:471] (~22)
- [ ] `delete:` `setTopLevelWindow` + dead `'focus'` dispatch branch. [InputPlotWindow.py:141] (~8)
- [ ] `yagni:` `last_requested_state` property → plain attribute (no external readers, no locking added); BLACS_DIR try/except-ImportError fallback (blacs/blacs.py never existed post-2019); spec-is-None guard in device registry (keep `module_num += 1` unconditional). (~18)
- [ ] `shrink:` KillInstance guard + `PlotWindow().Instance()` throwaway; write-only `Legend.items`; write-only `StateQueue.qt_mainloop_instantiated` (**replace `queue_inmain` body with `pass` — the method itself is the Qt-startup barrier, do not delete**); dead assignments (`res = {}` at device_base_class.py:681, `plot_win = None` at InputPlotWindow.py:69 — auditor's line numbers corrected). (~10)
- [ ] `delete:` `DataReceiver.last_frame_time`/`frame_rate`/`update_event` + unused `PlotWindow` import (drop only `UiLoader` from the qtutils line — `inmain_decorator` is live). [NI_DAQmx/blacs_tabs.py] (~5)
- [ ] `shrink:` `_reset_data_socket` dedup — init must set `self.data_socket = None` before first call. [NI_DAQmx/blacs_workers.py:520] (~5)

### analysislib smalls + tooling

- [ ] `shrink:` opencell Front/Cell copy-paste → loop (re-run the routine on a recent h5 before re-enabling; it's registered at flag 0); multishot commented blocks + unread `image_data_nuvu`/`count` (run the multishot once after); axis-styling helper ×5; spectroscopy branch merge; `_print_summary` (stdout always discarded by the widget wrapper); StringIO boilerplate ×4; unreachable `_MODULE_STATE` fallback; `_avg_integrate` → return tuple; import hoists (**keep `import ipywidgets` local** so scan_plots imports outside a kernel); `sosfreqz`; unread `YAG_DELAY`; NI_SCOPE argparse `__main__`; Ch0/Ch1 h5-layout fallback + `_extract_time_value` (**keep the `_resolve_fs_hz` attrs→CT fallback** — pre-attrs files need it); lyman29/analysis.py dead blocks. (~280)
- [ ] `shrink:` `jim_DIO_acquire.py` lines 1-126 (commented CT copy; live CT is one directory up). (~134)
- [ ] graphify `postmerge_fix.py`: single-pass filter+Counter, `functools.lru_cache` for `_import_cache`, f-strings for phase3 dicts, drop the orphan-stub subset pass. (~29)
- [ ] `yagni:` pre-push lines 44-50 conditional → two-path literal `TEST_PATHS` (the "rolled back" comment is stale; external_gui_lib/tests exists and is tracked). **Takes effect only after `cp .githooks/pre-push .git/hooks/pre-push`; each of the ~8 live worktrees needs its own reinstall.** (~6)

### Unvetted but well-evidenced (spot-check before applying)

- [ ] `delete:` `ScanAnalysis.single_trace()` — only references are commented-out cells. [scan_plots.py:822] (~35)
- [ ] `shrink:` `RemoteAnalogOut`/`RemoteAnalogMonitor` same-class-twice → subclass. [RemoteControl/labscript_devices.py:119] (~40)
- [ ] `shrink:` four near-identical read loops → `_read_values(connections, skip=None)`. [RemoteControl/blacs_workers.py:580] (~35)
- [ ] `yagni:` `open_retry_delays()` 4 kwargs + 4 module constants nobody overrides → `DELAYS = [3.0, 5.0]`. [NuvuCamera/_helpers.py:84] (~37)
- [ ] `shrink:` `program_value`/`check_remote_value` duplicated raise→v1-dict translation → helper. [RemoteControl/blacs_workers.py:340] (~24)
- [ ] `shrink:` `_compute_od` → reuse `filtering.process_trace`; scope pre-trigger algebra → `-0.01 * time_ms[-1]`; stored-scans double-write (keep `w['stored']`); `_load_summary_html` shares numbers with `_print_summary`. [scan_plots.py, scan_explorer_widgets.py] (~36)

---

## Tier 2 — Conditional cuts (each gated; decide per line)

- [ ] **lyman29 trees** — labscriptlib (~1,802) + analysislib byte-dups `test.py`/`benchmarking.py` (~123). Gates: lyman29-team confirmation; sequences are provenance for `analysislib/lyman29` notebooks; only in the same commit as (or after) the legacy-sequences cut.
- [ ] **repo-root tests/ spike scripts** (~798) — five distinct one-offs whose design shipped 2026-07-30. Gate: 4 docs/handoffs cite them by path as A1–A15 evidence → accept dangling links.
- [ ] **Legacy sequences** `Just_Yag`, `BaF_scanning`, `BaF_Fluorescence_Raster` (~418) — verified non-compiling against current CT. Gate: `.claude/rules/sequences.md` says "don't archive or delete" → **amend the rule in the same commit** or the next agent restores them.
- [ ] **Backup CTs** `closed_cell`, `fromLyman`, `photon_counting` (~425) — tracked & clean, git has them. Gates: same sequences.md amendment; record recovery hashes; confirm photon-counting config won't be revisited. (`open_cell2` is NOT in this list — see Rejected.)
- [ ] **`initialise_GUI`/`initialise_workers` template-method collapse** (~210) — real duplication, but tabs genuinely diverge (BigSky voltage-only widgets/no stacked widget; Rastering `_monitor_labels`; LaserLock skips AO-for-monitor creation). Gate: design with ≥3 hooks and preserve `_init_subscriber_registry()` before `super().__init__()` (the 2026-05-26 failure class).
- [ ] **`old_environment.yml` ×2** (~132) — gate: first write the known-good pins (pyzmq 23.2.0, numpy 1.26.4, python 3.11) into docs/.
- [ ] **`lessons_with_shafin*` + benchmarking analysis scripts** (~148) — gate: PI sign-off (onboarding material).
- [ ] **`_helpers` one-expression wrappers + tests** (~80) — they are the tested SDK-free seam the pre-push hook enforces (`snap_should_retry` = the 214-timeout retry budget). Gate: move the coverage with the inline.
- [ ] **mock tab branches** (~24) — gate: flip `mock=True` default → `False` in `RemoteControl.__init__` (labscript_devices.py:248) in the same cut (else a CT omitting `mock=` silently never connects). Keep `InMemoryTransport` + worker mock server (test surface).
- [ ] **`RemoteRetryableError`/`RemoteMalformedReplyError`** (~30) — behaviour-neutral. Gate: amend remotecontrol-zmq-protocol-v2.md:22 which names them as canonical surface.
- [ ] **BigSky `_query()` + `getState()` tables** (~80) — gates: keep the nonsense-mode→standby fallbacks; never hold `_stateLock` across setter callbacks (non-reentrant → GUI deadlock); update `test_zmq_v2_protocol.py` mock surface same commit.
- [ ] **BigSky green-echo into `_sendCommand`** (~24) — gate: accept semantics change (green = "bytes returned", not "parsed OK") and document it.
- [ ] **queue `yield` boilerplate collapse** (~20) — gates: result must stay a LIST (bare yield flips to old_worker_flow and breaks `raw_results[0]`); exclude the 2 non-boilerplate sites (transition_to_buffered's `transitioned_called` + differing force-reprogram attrs; abort iterates its own arg). Validate with ≥3-shot queue + mid-queue abort.
- [ ] **`set_status` removal** (~13) — git intent confirms deliberate perf strip. Gate: also fix `plugins/cycle_time/__init__.py:104,116` (would AttributeError) and delete `get_status` + its meaningless read at :584.
- [ ] **`create_subset_widgets` collapse** (~10) — gate: accept converting a loud ValueError (4-tuple branch) into a silent 3-tuple; no subset tab populates `self._image` today.
- [ ] **`queued_experiments` try/except** (~4) — gate: accept GUI-thread failure at quit surfacing as "queue paused" instead of defaulting to more-shots.
- [ ] **rastering caveated items**: calibration-label method delete (~18; bake the `lx`/`ly`/`group_move` strings into the .ui first), `_phys_to_slider` reuse (~15; gamma slider is 1..1000 offset-origin), AOI sync loop (~14; keep the ÷4 snap one-directional), module-level `camera` import (~1; **pyueye-before-PyQt5 DLL load order** — cut only with a relaunch verify, or drop the local import instead), pytest runners + `_Skip` shims (~64; drops pytest-less `python tests/x.py` mode — rank last, it's the cheapest way to exercise the stub tests).
- [ ] **`_within_bounds` dedup** (~6) — signature mismatch means the cut roughly breaks even and removes the controller-side seam both bounds systems pass through; skip unless touching that code anyway.
- [ ] **`Launch Labscript.bat`** — cut ASCII-bar cosmetics only (~25). The polling loop + `%TEMP%` markers are the 30 s launch-failure detector (`:FAIL` branch) — keep.
- [ ] **`.claude/backup-memory.sh`** (~7 + 10 stale files) — gate: accept losing the only in-repo snapshot of auto-memory.
- [ ] **HF `_voltage_dirty` machinery** (~12) — write-only, deliberately added (cbd32d9) as defensive twin. Gate: leave a one-line pointer at the `textEdited` site to the press→defocus race it guarded.
- [ ] **HF `restore_settings` table + slot merge** (~9 net → ~2) — only pays bundled with the registry-loop shrink; keep both `@pyqtSlot` bound-method entry points as thin wrappers (thread-affinity for AutoConnection).
- [ ] **HF config.py logging→print** (~2) — gate: `.warning` currently reaches stderr via lastResort; this changes stream, not a pure no-op.
- [ ] **`scan_analysis.group_and_subtract`/`baseline_correct_batch`** (~79) — zero calls verified, but an archive notebook imports the names. Gate: accept the archive breakage explicitly (API Stability Rule).
- [ ] **shared `shot_setup.py` for lyse boilerplate** (~65 → less) — do the deletions first (only 3 live copies remain), keep the helper in Main_Experiment/ (lyse puts script dir on sys.path), re-run all three registered routines.
- [ ] **example IMAQdx template dedup** (~46) — only the two analysislib copies are identical; the labscriptlib one is a different file. Delete one analysislib copy only.
- [ ] **`_GRID_ON`/`set_grid`** — operator toggles it from a notebook. Swap internals to `plt.rcParams['axes.grid']`, keep `set_grid` as a one-line shim. (~7 not 12)

---

## Tier 3 — REJECTED by domain vetting (do not cut)

| Claimed cut | Why it survives |
|---|---|
| scan_plots .npz cache layer (~260) | downsample/time_window/exclude wired to live explorer widgets; `allow_pickle=False` is the portability guarantee; 7 real caches in Dropbox |
| `interactive_bounds` inline fallback (~150) | explorer switches to `%matplotlib inline` in later cells → fallback is the path actually taken; SpanSelector branch would AttributeError there |
| `Abs_data.py` (~119) + NI_SCOPE batch loaders (~118) | two offline toolchains are BOTH current (03_27/04_01 notebooks vs explorer chain); neither supersedes the other |
| analysis.py commented NI_SCOPE subplot (~25) | NI_SCOPE re-entered the CT in fc810b7 — the snippet is about to be needed; only `YAG_DELAY` is cuttable |
| `connection_table_open_cell2.py` (~224) | created BY fc810b7 as the deliberate open-cell swap-back archive |
| `sequences/Open_cell.py` (~67) | supersession inverted: it's the complete sequence; `Open_cell2.py` is a 28-line stub with hardware commented out |
| `sequences/Closed_cell_scan.py` (~63) | the ONLY sequence wired to the live `scanning` globals group — deleting removes scan capability |
| BigSky `_applyState` table (~85) | six bodies differ in safety-load-bearing ways: `dangerMode` gate on Q-switch arm, standby's 3-attr cache clear, ZMQ interlock REJECTED returns. Salvage: ~20-line send+cache+echo core with guards left in callers |
| BigSky `aboutToQuit` handler | closeEvent does NOT fire on `QApplication.quit()`/session end — this is the only `>s` standby + serial-close net on those paths; failure mode is lamps firing after unattended shutdown |
| BigSky `_updateTemperatureStatusColor` in updateTemp | `confirmFrequencySetting` and `toggleTerminalInput` also call updateTemp with no indicator refresh after |
| HF hand-rolled Y autoscale → pyqtgraph autoVisible (~60) | InfiniteLine.dataBounds makes setpoint AND ±tolerance lines unconditional bounds contributors → "Incl SP" untoggleable, y-span floored at 2× tolerance (halves in-lock resolution on TiSa_1); also re-introduces per-frame tick relabelling across 16 plots on the 33 ms path |
| HF console stdin-fallback for restore dialog (~50) | commit 0a9afaa documents the real lab failure ("diff found, no dialog appears", multi-monitor Win11); it's the only escape from a modal that blocks startup |
| `math.isclose` for config diff (~2) | default rel_tol=1e-9 at ~350 THz ≈ 350× loosening → silently hides real setpoint drift |
| `.pth`/pip -e replacing the `_EXTERNAL_LIB` shim (~30) | moves tracked 8-line shim into untracked per-env config that vanishes on env rebuild + forces import rewrite across 3 repos; deletes nothing |
| zmq_v2 `_handle_ping` + `RequestIdCounter` | PING is documented v2 (spec §3.2) with a live cross-repo test; RequestIdCounter has a production caller (RemoteControl/blacs_workers.py:154) |
| NuvuCamera `on_restart` → `@define_state` (~18) | restart callback runs synchronously on the GUI thread just before worker teardown; a queued state event would never arrive — the manual blocking queue push/pop is required |
| NI_SCOPE `abort_buffered`/`abort_transition_to_buffered` deletion | required worker entry points queue_work'd by name on every abort (aliasing form above is the safe alternative) |
| `AnalogInput.self.plot` → `plot_process is not None` (~4) | lifetimes differ during the modal plot-selection exec_() window; the swap turns safe no-ops into "plot line_id not added" crashes |
| `subagent-source-discipline.ps1` inline (~6) | inline settings.json command spawns the identical pwsh process; inlining quoted JSON into JSON is an escaping hazard |
| NI_SCOPE `quick_tree` (~15) | called from live notebook cells; a Claude skill / h5ls isn't callable from a Python cell |
| NI_DAQmx `manual_mode_task` flag (~7) | NOT equivalent at post_experiment error paths — this is a latent BUG the flag currently causes; land as a bug fix with a shot test, not cleanup |

---

## Adjacent correctness findings (out of ponytail scope — route to /code-review)

1. **BigSky `_remoteSetVoltage`** (BigSkyControllerAmbitious.py:973): bare `return` on voltage parse error → `None` → `_handleRemoteCommand` reports **SUCCESS to BLACS** for a failed write.
2. **Rastering main-window flip checkboxes** (raster_gui.ui:43/53): connected to nothing — clicking does nothing; the camera dock's `flip_x_cb`/`flip_y_cb` are the live controls.
3. **NI_DAQmx `manual_mode_task`** (blacs_workers.py:775): early raise in post_experiment leaves flag True with task None → next buffered transition raises 'Task not running'. Fix = `self.task is not None` + ≥3-shot queue test with mid-queue abort.
4. **Rastering `ui_path`** (main_rastering.py:71): relative path resolves against launcher CWD, not `__file__` — the only real widget-drift channel found.

---

## Review of the agent assessments

**Corroboration:** the two duplicate audits (analysislib ×2, user_devices ×2 — an interrupted-then-relaunched pair that both completed) agreed on ~85% of items; the relaunches added the decisive evidence (lyse.ini registry, md5 checksums, string-path wiring checks). Cheap insurance that paid off.

**Vetting value:** 7 domain passes killed ~1,600 lines of confident-looking cuts. Every cluster contained at least one live-breaking claim. The five recurring premise errors in the raw audits:

1. *Gitignored-notebook callers ⇒ dead* — `.gitignore` excludes `*.ipynb`, so the entire live offline workflow is untracked (analysislib, ~650 lines of false positives).
2. *Recency ⇒ supersession* — in this lab the newer file is often the stripped-down WIP; the near-misses were `Closed_cell_scan.py` (scan capability) and `connection_table_open_cell2.py` (the swap-back).
3. *Textual similarity ⇒ collapsible* — BigSky's six command bodies differ precisely in the safety guards.
4. *No static caller ⇒ dead* — misses side-effect-load-bearing code: `aboutToQuit`, DLL import order, Qt/BLACS by-name entry points.
5. *Native-feature parity assumed* — pyqtgraph InfiniteLine bounds, `math.isclose` rel_tol.

**Adjudications (my calls where sources conflicted):** NI_SCOPE abort methods kept via the aliasing form (auditor #2's proposal survives blacs-expert's objection to deletion); `analysis_old.py` delete stands on lyse.ini authority despite the vetter's trace-name correction; mock machinery resolved as branch-cut + default-flip + keep-test-surface; `updateAllStatusIndicators` table confirmed but explicitly scoped away from the interlock chain.

**Coverage gaps, stated plainly:** the GUIs auditor's two sub-readers died silently, but the two peer sessions (raster-ui-auditor, bigsky-hf-auditor) covered exactly those files — no net gap. Deliberately not flagged: the three `serve_once` circuit breakers (policy divergence, not bloat), `HF_Locking/tools/` (documented operator tooling). Not audited at all: non-registered GUI dirs. Six "unvetted but evidenced" items above never passed a domain vetter — spot-check before applying.

## Process notes before applying anything

- **Remove the stale `HF_Locking-zmq-v2` worktree first** (or duplicate every HF edit into it) — it holds byte-identical copies at the same line numbers and will make the next grep-based audit re-report all 21 HF findings.
- Backend cuts touching the POST_EXP/queued-shot path (queue yield collapse, set_status, manual_mode_task): batch on one branch, validate with a ≥3-shot queue + one mid-queue abort — never a single shot.
- HF display.py items need a live-GUI eyeball; config.py items need verification against a real `pid_config.json` diff (that path silently mis-restores PID gains if wrong).
- Pre-push hook edits require re-installing the copy (`cp .githooks/pre-push .git/hooks/pre-push`) in this checkout and each live worktree.
- Cuts gated on `.claude/rules/sequences.md` must amend the rule in the same commit.

**net: ~11,000 lines confirmed (+ ~4,300 conditional), −0 deps, −6 stale worktrees (~22 MB), −1 tracked binary.**

---
*Audit run 2026-08-12 by ponytail-audit; 9 audit passes, 7 domain vetting passes (blacs-expert ×2, lyse-analysis, amo-expert, ablation-tech, BigSky laser-controller, HF_Locking). Report only — nothing applied.*
