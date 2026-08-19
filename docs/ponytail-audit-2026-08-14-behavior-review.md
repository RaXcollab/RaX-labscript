# Ponytail Audit — Behavior & Risk Review (2026-08-14)

Independent re-verification of every cut proposed in `docs/ponytail-audit-2026-08-12.md`,
two days after the audit, against current code. Seven domain verification passes (whole-trees ×2
corroborating, user_devices ×2 corroborating, rastering, BigSky+HF, backend forks via blacs-expert,
analysislib via lyse-analysis, Tier-2/repo). **Report only — nothing applied.** Repo tips at review
time: parent `8134dba`, rastering main `306a8ff` (ui-redesign merged **after** the audit), HF `4fafdcd`,
BigSky `98ff562`, blacs `81316aa`, labscript-devices `b32c97e`, labscript-utils `25cee8c`.

## Behavior classes (the "physics terms" legend)

Every item below is tagged with one of four classes describing what actually changes in the lab:

- **[0] No physical change** — the code never executes during data taking. Photon-for-photon,
  shot-for-shot identical experiment. Deleting it changes disk contents only.
- **[D] Display/log only** — what the operator *sees* (labels, log lines, banner text, plot padding)
  changes; what the hardware *does* is untouched.
- **[E] Error-path semantics** — a healthy shot is unchanged; what changes is *when and how a
  failure becomes visible* (loud pause vs silent skip, red tab vs warning, which garbage a parser
  tolerates).
- **[P] Physical/workflow reach** — applied as written, this would change hardware behavior,
  crash a control GUI, corrupt recorded data, or block the lab workflow (pushes/tests).

## Headline

| Outcome | Count (≈) |
|---|---|
| Confirmed safe as written | ~40 items |
| Safe, but the audit's instructions are incomplete/wrong in a way the applier must know | ~24 items |
| Disputed / must be rescoped or dropped | 12 (R1, M, B2, B4, K8, K10, T3-rationale, B-fps, Y15-1, Y19, Y7, Y3) |
| Genuine behavior changes to accept knowingly | 7 items (B5-lpm, B7, H6, K12, Q-half, I-log-lines, P) |
| Stale — superseded since the audit | T9 (pre-push), R-section counts, Y20 (partial), correctness-finding #2 |
| Explicitly NOT verified — do not apply on this review's authority | Y4 (spectroscopy merge), Y12 (lyman29 blocks), Y11's old-layout claim |

**The six hard traps** (each would bite if the audit is applied literally):

0. **`_compute_od` → `filtering.process_trace` (unvetted scan_plots item) — REJECT.** Not the same
   math (intercept kept vs removed, ratio+log vs subtraction, 5 ms vs 1 ms fit tail). Applied, the
   OD pipeline divides by a ≈0 baseline, the non-finite clamp fires, and **every reported optical
   depth silently becomes 0.0 — no crash, no error, just wrong physics numbers**. [P]
1. **`NI_SCOPE/__init__.py` must be emptied, NEVER deleted** (Tier-1 line 42). Deleting it makes
   NI_SCOPE a namespace package and collides its `tests/` module names with NuvuCamera's under the
   pre-push aggregate run — **collection error, every push from the parent repo blocked**. Proven
   empirically (control: 134 collected; treatment: `ImportPathMismatchError`, 0 collected). The
   space-file half is safe (`git rm`, it is tracked). [P]
2. **`millisecond_to_fps` is NOT dead** (Nuvu dead-surface list). Live chain:
   `blacs_workers.py start_continuous_acquisition → set_fps → millisecond_to_fps`. Deleting it as
   listed = `AttributeError` the moment EMCCD live view starts — you lose the ability to watch
   beam/target alignment live. Delete the whole `__real_fps`/`real_fps`/`millisecond_to_fps` cluster
   together or not at all. [P]
3. **Rastering `hasattr` bulk-delete (R1) would crash the GUI at launch.** The premise ("every
   named widget exists in raster_gui.ui") was never true and the ui-redesign made it worse: of 75
   current guards only ~32 name real .ui widgets; the redesign *deleted* `flip_x/flip_y_checkbox`
   from the .ui, making those guards the only assignment path. Mechanical application = no ablation
   control until reverted. Rescope to the ~30 verified-in-.ui subset minus 3 stub-required guards. [P]
4. **BigSky `>lpm` parser unification is a safety-reach behavior change, not "misc confirmed".**
   The proposed trailing-int regex accepts three garbage serial-reply shapes the current strict parse
   rejects (concatenated double-read, stale prior reply, leading echo — all real shapes for this
   controller). Accepted garbage can newly route into the nonsense-mode→standby fallback, which sends
   `>s`: **a mangled readback could stand the ablation YAG down mid-run** (lamps stop → molecule
   production stops). Keep the strict parse; unify code shape only, or leave `>lpm`/`>qsm` alone. [P→E]
5. **`RemoteAnalogOut`/`Monitor` merge is direction-critical** (unvetted item). The h5
   `remote_device_operation` table — the **authoritative scan x-axis** for all analysis — is gated by
   `isinstance(device, RemoteAnalogOut)`. `Monitor(Out)` lets monitor channels leak into that table
   (or compile-crash); `Out(Monitor)` — or a shared private base — is inert. Today no sequence sets a
   monitor, so the corruption is one line away, not present. Mandate the safe direction or skip. [P]

**Audit process notes corrected:**

- The "each of the ~8 live worktrees needs its own pre-push reinstall" note is **wrong**:
  `core.hooksPath` is an absolute path in the shared `.git/config`, so all ten parent-repo checkouts
  execute one hook file. One `cp` covers everything. (GUI repos are separate and never run this hook.)
- The pre-push TEST_PATHS item itself is **~70% stale** — the glob landed in `8134dba` after the
  audit; only a 3-line always-true conditional (+2-line stale comment) remains flattenable, and the
  installed copy is already in sync.
- "Remove `HF_Locking-zmq-v2` worktree first" still stands (un-actioned). Its copies are
  content-identical to HF main (EOL differs on `main_wlm.py`/`display.py`; same line numbers).
- A **7th rastering worktree now exists**: `rastering-ui-redesign` (05ce782) — created after the
  audit, now merged into main and clean; same removal profile as the audited five. The audit's KEEP
  on `rastering-atomic-xy` (491b0ca, still 1 ahead, unmerged) re-verified and stands.
- **Nothing in rastering/HF is pushed** (rastering main ahead 15 of origin). Worktree removal is
  safe (all tips are ancestors of local main), but push before pruning branches.

---

## Tier 1 — Whole trees / files (audit lines 31–42)

Physics framing for the whole cluster: none of these directories participate in a shot. BLACS
builds device tabs from `userlib/user_devices` (the live registry), lyse runs only the scripts
named in `app_saved_configs/Main_Experiment/lyse/lyse.ini`, and the rastering GUI reads its live
calibration from the top-level `calibration_data.json`. Deleting all of it changes zero photons.
The traps are archival and workflow-level, not physical.

| # | Item | Class | Verdict | Notes / traps |
|---|---|---|---|---|
| 1 | `GUIs/rastering/Old Code/` | [0] | Safe **with trap** | **`lyman_calibration_data.json` inside it is UNTRACKED** (`.gitignore:2 *.json`) — "git history preserves it" is false for that one file; it is the lyman-era ablation-target pixel↔motor calibration map. Copy it out first or accept irrecoverable loss. Also update `gui-rastering.md` digest (its "README still points at it" line is stale — README is clean). |
| 2 | `labscript-devices/.../RemoteControl/` (dead twin) | [0] | Safe, audit rationale wrong ×3 | (a) BLACS **does** walk+exec its `register_classes.py` each start — it just registers nothing (0 non-comment lines); (b) un-commenting it would **crash BLACS with a duplicate-registration ValueError**, not silently shadow; (c) doc blast radius is 6 files, not 1: `device-builder.md:37,39` (not :38), `blacs-device-patterns.md`, `remotecontrol-zmq-protocol.md:19-20` (which records a deliberate *keep* decision being overridden — fine, it's the deprecated v1 doc, but say so), `rollback-2026-05-26-revival-inventory.md`, graphify `postmerge_fix.py`/`verify_fix.py` (degrade to no-ops), `labscriptlib.md` digest. Two `.bak` files import it (unimportable, inert). |
| 3 | `userlib/labscriptlib/main_experiment_control/` | [0] | Confirmed safe | Imports point outward only; not on any labconfig path; NI_PXIe_6739 orphan concern re-confirmed clean. Includes 8 RunManager globals `.h5` files. |
| 4 | `Jupyter notebooks/_build_*.py` | [0] | Confirmed safe, premise softened | Both scripts `FileNotFoundError` today, but the source notebook lives in `archive/` — they are *dormant*, one `cp` from running. Delete them **because** reviving them would clobber ~650 KB × 3 of hand-edited operator notebooks (44× grown since generation), not because they're unrecoverable. |
| 5 | 6 stale GUI worktrees + empty dir | [0] | Confirmed safe; list now 7 | All five tips re-verified ancestors of current mains; `rastering-atomic-xy` re-verified UNMERGED (KEEP). Add `rastering-ui-redesign` (merged post-audit). Use `git worktree remove` (not `rm -rf` — orphans `.git/worktrees` admin dirs); `rastering-stepping` is a plain empty dir, `rmdir` correct. **Push first** — commits exist only on this machine. Sequence before item 6 (HF worktree holds copies of item-6 files). |
| 6 | `GUIs/HF_Locking/diagnostics.py` | [0] | Confirmed safe | Never imported anywhere; `ENABLED=False` besides. The two CLAUDE.md mentions exist per-tree — doing item 5 first makes it two edits, not four. |
| 7 | `userlib/labscriptlib/example_apparatus/` | [0] | Confirmed safe | `example.ini` never loads on RAX-CONTROL. Orphan the audit missed: `app_saved_configs/example_apparatus/blacs/RaX-Control_BLACS.h5` — matching saved-state tree, delete together. Keep `example.ini` itself (documents the labconfig schema). |
| 8 | `analysis_old.py` | [0] | Confirmed safe | Registry authority located and read: `app_saved_configs/Main_Experiment/lyse/lyse.ini` lists `analysis.py`, `analysis_opencell.py`, `analysis_opencell2.py`, `analysis_multishot.py` — `analysis_old.py` absent; zero hits across all 60 notebooks on disk. Update 2 agent-memory digests same commit. |
| 9 | `.claude/_compare_rastering_sessions.py` | [0] | Confirmed safe | Hard-coded UUIDs, zero references. |
| 10 | `project_filebrowser.db` | [0] | Confirmed safe | Tracked Navigator cache. The `.gitignore` half is **mandatory** (no `anaconda` entry exists → Navigator re-adds it as churn). Same-class junk the audit missed: `userlib/user_devices/NI_SCOPE/.vs/` (tracked Visual Studio index binaries). |
| 11 | Empty `common/` packages ×2 | [0] | Confirmed safe | Both `__init__.py` are 0 bytes; zero importers; not namespace-package anchors. |
| 12 | `"__init__ .py"` space file + NI_SCOPE banner | [P] | **Split — see trap #1** | Space file: safe, it's tracked → `git rm` (Python ignores it; `user_devices` stays a namespace package either way; the old "don't rename" caution is about *renaming*, which would change every device-test module path — deletion is inert, empirically 134→134 collected). NI_SCOPE `__init__.py`: **truncate to 0 bytes** (matching the other four devices), never delete — file *presence* is load-bearing for pytest module naming. |

## Tier 1 — user_devices + external_gui_lib (audit lines 46–56 + unvetted 102–107 + Tier-2 120–122)

Physics framing: these classes are the BLACS side of the three external GUIs plus the EMCCD/scope/
counter drivers — the code that programs hardware per shot (`transition_to_buffered`), reads it back
(`post_experiment`), and echoes state to the panel. Verified: none of the cuts touch what gets
programmed or recorded on a healthy shot. The traps concentrate in (i) things that look dead but
sit on live chains (camera FPS), (ii) by-name dispatch (aborts), and (iii) the h5 schema gate
(analog-class merge).

- **A. nc_camera `_call()` shrink — [0], rescope.** Error policy is already centralized in
  `errorHandling` (the 107/27/214/215/216 no-close rules live there, uniformly invoked), so a
  uniform helper preserves camera-recovery behavior. But 5–8 of the ~35 methods have bespoke try
  bodies that must stay outside the helper — above all **`closeCam(noRaise=True)`**, which
  `errorHandling` itself calls; folding it in creates a raise-inside-error-handling loop (a camera
  error during teardown would cascade instead of closing cleanly). Also `read` (extra print),
  `camIsAcquring` (returns a value), `setSquareBinning` (two SDK calls), `openCam` (extra state).
  Net saving ≈ 28×4 lines, not 150. Out-params fine (byref built at call sites).
- **B. Nuvu dead surface — [P] one sub-item, rest [0]/[D].** See trap #2 (`millisecond_to_fps`).
  Rest verified dead (`saveImage`, `setRawEmGain`, `getControllerTemp`, `camIsAcquring` — only a
  commented caller, `purgeBuffer`, `updateCam`, `get_image64`, macAdress branch, dead defines).
  Counting nits: 8 (not 9) NC_api prototypes dead now, +4 more become dead once wrappers go (12
  total); **`ncCamFlushReadQueues` (plural) is dead, `ncCamFlushReadQueue` (singular) is LIVE** —
  one-character trap. Module-level `matplotlib.pyplot` removal is a pure win: every camera worker
  subprocess currently pays a full pyplot import (~0.5–1 s, tens of MB, GUI backend in a headless
  worker) — imaging behavior unchanged, BLACS starts lighter. `disconnect_if_error` removal is [D]:
  its `raise e from None` currently suppresses exception chaining, so BLACS.log camera tracebacks
  get *longer* (chained context) after removal — better forensics, same hardware handling; update
  `docs/known-latent-issues.md` same commit.
- **C. Commented predecessor classes — [0], confirmed.** Pure leading comment runs; keep NI_SCOPE's
  file-header banner line.
- **D. conftest consolidation — [0] production, workflow change.** "Byte-identical" is false
  (5 distinct md5s — docstrings differ) but the executable 9 lines are identical, so the premise
  survives. Empirically verified (pytest 9.0.3): hook glob from repo root works with a single
  `userlib/conftest.py`; `pytest userlib/user_devices/X/tests` from repo root also works;
  `cd` into a tests dir breaks (rootdir/confcutdir stops below userlib). Fragility: rootdir is
  cwd-derived **only because no pytest ini/pyproject exists anywhere** — adding one later silently
  breaks the scheme. **Coupled with J**: `test_zmq_v2.py`'s docstring documents (and its `__main__`
  self-runner automates) exactly the broken workflow — rewrite both in the same commit.
- **E. `MultiStaticOutputValue` — [0], confirmed.** One occurrence repo-wide (the def). Delete
  before/with any RemoteAnalogOut change (it references the name).
- **F. Dead monitor-read surface — [0], confirmed dead, blast radius bigger.** The claim survives
  full re-verification: `status_monitor` is registered with no timer anywhere (complete
  `statemachine_timeout_add` + `queue_work` string inventories taken); the tab's
  `_pubsub_monitor_cache` is write-only; shot-h5 `monitor_values` comes from the **worker's**
  `_pubsub_cache` — a third, untouched path. Physics: the panel numbers and the h5 record are
  produced by the live 5 s/500 ms `check_remote_values` poll and the worker cache respectively;
  the deleted poll has never fired once. Audit misses: **two pre-push tests die**
  (`test_worker_typed_status.py:58-65, 79-85` call the two methods directly — push blocked without
  same-commit edits); RasteringDevice's own `_pubsub_monitor_cache` init+write
  (`RasteringDevice/blacs_tabs.py:104,339`) must go too; `test_tab_registry.py` "repoint" is
  actually a one-line delete (`:23`); doc list additionally includes `docs/device-internals.md:52,60`
  (path-scoped auto-load — highest poisoning risk), `PATHFINDER zmq-bridge.md`, v1 protocol doc,
  cutover review, `remotecontrol-family.md` digest; `frame-explicit-coords-design.md` is **untracked**
  (can't be "updated in the same commit" until added). It also reverses a written 2026-05-05 design
  "KEEP" — get a one-line operator ack. Bonus worth stating in the commit: deleting `check_status`
  removes the base worker's only *raising* read path, closing the documented "raising poll bricks
  the tab" latent hole.
- **G. BigSky `enter_warmup`/`exit_warmup` — [0], confirmed.** No callers, no `queue_work` strings;
  live warmup/arm paths (`send_action`, `restore_warmup_from_tab`, `_arm_laser`) verified separate
  and tested. Physics: no change to when lamps warm or arm — these two were never in that chain.
- **H. BigSky tab shrink — [0], confirmed.** Predicate ×3 semantically identical (site 3's local
  `enabled` ≡ `self._input_enabled`, assigned first); keep its `else` branch for non-prefix combos.
  `_btn_style(bg,fg)` covers exactly the 4 copies — do NOT extend to the `padding: 6px` toggle pair.
  The 3 constants are never read anywhere (worker's `_COMMAND_SUFFIXES` is a different, live name).
- **I. Pure-delegation/dead overrides + NI_SCOPE abort aliasing — [0] deletions, [D] aliasing.**
  All delegations verified pure; `global NuvuCam` dead; unused imports exact. BLACS dispatches
  `abort_buffered`/`abort_transition_to_buffered` **by string** (`device_base_class.py:710,724,726`,
  driven from the queue's abort paths) — outright deletion would make "Abort" silently not abort the
  scope (veto correct); class-attr aliasing preserves the entry points. Cost: the worker log loses
  the two lines saying *which* abort path fired (`[NI_SCOPE] abort_buffered()` vs `..._transition...`);
  keeping three one-line defs instead costs 4 lines and loses nothing — operator's call.
- **J. zmq_v2 safe subset — [0], confirmed.** All three GUIs import exactly
  `RemoteControlServerBase, handler, encode_reply, PROTOCOL_VERSION, ZmqRepTransport` from the ONE
  live `zmq_v2.py` (sys.path, no copies); `Transport` is a type-hint only (no isinstance /
  runtime_checkable anywhere; `from __future__ import annotations` present — retype `:327` when
  deleting); `client_matches_advertised` zero production callers, **but its name is in
  `test_zmq_v2.py:40`'s import — stale import = collection error = push blocked**; `v1_refused_reply`
  one caller; `__main__` runner actually lives in `tests/test_zmq_v2.py:442-445` (audit filed it
  under zmq_v2.py). PING + RequestIdCounter stay (production caller re-verified).
- **K. `_pairs` + `require_group` — [0] with one guard.** `_pairs` 4-tuple → dict is exact
  (unused fields, insertion order preserved → identical widget order). RemoteControl try/KeyError →
  `require_group` equivalent (divergence only when the path exists as a Dataset — both fail today,
  different exception type). **edge_counter half needs a guard**: `'/'.join(parts[:-1])` is `''` for
  a single-segment `save_path` and `require_group('')` raises where the current loop correctly
  no-ops — the default path has 3 segments so the bug would ship silent. Keep the `del grp[dset]`
  overwrite semantics. h5 output byte-identical → analysis unaffected.
- **L. Analog-class merge (unvetted) — see trap #5.** Direction-verified: class-NAME string dispatch
  (`device_class == "RemoteAnalogOut"` in all four tabs, connections.py compare) is unaffected by
  subclassing; the single `isinstance` gate at `labscript_devices.py:281` is what fills
  `remote_device_operation`. Physics: that table is what analysis reads as "what the sequence
  commanded" (laser setpoints, raster targets) — the one h5 table that must never contain readback
  channels. `RemoteAnalogOut(RemoteAnalogMonitor)` or a shared private base = zero change;
  `Monitor(Out)` = latent corruption. Re-declare the `description` strings either way.
- **M. Four read loops → `_read_values()` (unvetted) — DROP.** There are three read loops + one
  write loop, and their differences are the deliberate 2026-08 strict-read design: `check_remote_values`
  aborts the whole poll on timeout (suppresses partial front-panel writes), `check_all_remote_values`
  best-efforts, dead `check_status` raises, `program_manual` is a write path with the courtesy-write
  policy hook. **Apply F first and only one loop remains** — a helper for one caller. Physics of a
  naive merge: a ZMQ hiccup during the poll could write a half-updated set of panel numbers, or a
  refused read could brick a tab — exactly the failure classes the current asymmetry prevents.
- **N. `open_retry_delays` → literal (unvetted) — [0] production, test churn.** Schedule provably
  `[3.0, 5.0]`; production passes no kwargs. But this is the pre-push-enforced `_helpers` seam: two
  tests pass kwargs, two constants are asserted, and **`CAMERA_OPEN_MAX_ATTEMPTS` is also the
  default of `camera_open_failure_message`** (not free). Physics: the retry budget is the "camera
  was left powered off → error 27" recovery window; keep one assertion pinning `sum(delays) < 15 s`
  (the latency budget) against the literal.
- **O. v1-dict translation helper (unvetted) — [0], confirmed.** The two except-blocks are
  byte-identical (same 4-key dict); subclass exceptions already flow through. ~10 lines.
- **P. Mock-branch cut + default flip (Tier 2) — [E], upgrade, gate has zero instances.** Every CT
  in the repo passes `mock=False` explicitly, is commented out, has no RemoteControl device, or is
  BigSkyHub (own `mock=False` default). Flip changes nothing today; afterwards a future CT omitting
  host/ports fails **loudly at compile** instead of silently pretending to connect (shots would
  "run" with no hardware commanded — the failure mode being retired). Keep `InMemoryTransport` +
  `_MockRemoteServer` (test surface; note NuvuCamera's `self.mock` is an unrelated flag — don't touch).
- **Q. `RemoteRetryableError`/`RemoteMalformedReplyError` (Tier 2) — split.** Zero `except` clauses
  name either (full-workspace inventory) → control flow safe. `RemoteRetryableError`: genuinely
  inert, delete clean [0]. `RemoteMalformedReplyError`: **a message factory, not a stub** — its
  `__init__` builds the `malformed_reply` error dict so a corrupted ZMQ reply is reported as
  "malformed_reply", not misdiagnosed as "timeout". Deleting it without reproducing the dict inline
  changes the operator banner on exactly the failure it was built to disambiguate [D→E]. Keep or
  rewrite in place; amend protocol doc :22 either way.

## Tier 1 — GUIs/rastering (audit lines 60–67 + Tier-2 129–130)

Physics framing: this GUI steers the ablation spot across the molecule-production target
(camera-pixel ↔ motor-mm calibration, bounds, raster patterns that expose fresh target surface
per shot). **The redesign merge (306a8ff) post-dates the audit and rewrote ui.py/raster_gui.ui/tests;
`raster_controller.py` and `camera_settings_dock.py` are essentially untouched.** None of the valid
cuts touch path generation, clamping, bounds, or motion commands — the motion physics is unchanged
by everything below except where flagged.

- **R1. ~46 hasattr guards — DISPUTED, see trap #3.** Rescope: delete only guards whose widget is
  verified in the CURRENT `raster_gui.ui` (~32), keep the ~38 guarding runtime-created attributes,
  keep the 3 stub-load-bearing guards in `_update_step_mode_ui` (`goto_move_button`,
  `raster_remote_arm_button`, `group_jog` — the redesigned tests supply stubs without them), and
  note `flip_x/flip_y_checkbox` guards are now the ONLY creation path for those attributes.
- **R2. try/except-pass → `contextlib.suppress` — [0], count is now 13.** All 13 verified bare
  `except Exception: pass`. **Order after R7**: five additional *bare* `except: pass` (BaseException —
  NOT equivalent to `suppress(Exception)`) live inside the block R7 deletes.
- **R3. Controller dead code — [0], confirmed.** `cancel_calibration`, `request_stop` (Stop button
  still wired to `stop_raster` post-redesign), `segments_from_points` (actually in `raster_paths.py`),
  `list_device_serials` (actually in `hardware.py`) — zero callers via @handler routes, CommandType
  dispatch, ui wiring, or userlib. Physics: no live path can invoke them; stopping a raster and
  calibration cancel flows are unchanged.
- **R4. `build_controller()` fallback — [0], confirmed** (factory unconditionally defined; branch
  unreachable; redesign only touched theme lines in that file).
- **R5. `MotorResult` helper — [0], confirmed (25 sites)** — but `raster_controller.py` is the file
  the UNMERGED `rastering-atomic-xy` branch (491b0ca) patches: **rebase or merge that branch first**
  or eat a manual conflict. (Check first whether main's `_WRITABLE_PAIR` atomic-pair path already
  supersedes that branch.)
- **R6. Small shrinks — 6 of 8 valid.** `_sync_display_widgets` (2 byte-identical blocks + a bonus
  pair), `_set_flip`, nearest-point `min(range(...))` (tie-break identical), inline
  `_apply_image_scale`, name==key pairs, unused `typing.Optional` (camera dock only) — all [0].
  **`_move_reply` is mis-filed**: the duplicated reply block lives in `raster_controller.py`
  (~:411/:451), not ui.py. **`_user_home_both` caveat inverted**: atomic-xy does NOT touch ui.py —
  no collision; still move the atomic-move docstring to the connect site.
- **R7. Unreachable .ui fallbacks — [0], confirmed, all constructs survived the redesign.**
  `raster_continuous_checkbox`/`raster_step_button` are in the new .ui → creation fallbacks
  unreachable; `_auto_layout is None` branch unreachable (retires the old `# ponytail:` marker);
  five disconnect guards dead (`.ui` `<connections/>` empty, no `on_*` auto-slots, exactly one
  caller). Delete the whole fallback blocks — NOT just their hasattr conditions.
- **R8. Camera-dock pass-throughs + RasterDefaults + config aliases — [0], confirmed post-redesign.**
  The critical re-check passed: File-menu save-defaults writes a separate JSON
  (`save_user_defaults`), never `config.RasterDefaults` — the six fields (incl. `spiral_step`) and
  the 7 aliases + `_get("SERIAL_X")` fallbacks remain provably dead. Keep `rotation_changed`
  (index→k mapping = the image-rotation convention).
- **R9. Caveated items — mixed.** (a) **calibration-label method delete → DON'T** (was "gated"):
  the new .ui titles the group "Move (mm)" while the deleted method deliberately corrects it to
  "motor units" — cutting it ships a wrong unit label, re-seeding the px/mm confusion the CT
  mislabel saga just taught us. (b) `_phys_to_slider` reuse — [0], algebraically identical
  (verified). (c) AOI sync — [0], ÷4 snap one-directional preserved. (d) module-level `camera`
  import — the DLL-order rationale does NOT hold on the real launch path (`main_rastering` imports
  PyQt5 before ever touching ui.py); survives only as a duplicate-local-import cleanup (drop the
  `:620` local, keep `:28`); still relaunch once. (e) pytest runners + `_Skip` shims — [0] for the
  gate (pre-push never touches rastering; no CI), drops the `python tests/x.py` mode; the three NEW
  redesign tests already ship without runners (pattern abandoned); edit the "standalone-runnable"
  claim in rastering CLAUDE.md same commit.
- **R10. `_within_bounds` dedup — skip stands** (signature mismatch; the controller-side seam both
  bounds systems route through is worth keeping; both systems re-verified intact post-redesign).
- Audit's adjacent-correctness finding #2 (main-window flip checkboxes wired to nothing) is
  **already fixed by the redesign** (checkboxes removed from .ui). Finding #4 (`ui_path` CWD-relative)
  is still live.

## Tier 1 — GUIs/BigSkyControl (audit lines 71–75 + Tier-2 123–124)

Physics framing: this GUI owns the pulsed Nd:YAG ablation lasers over serial — flashlamp warmup,
Q-switch arm, standby, interlocks. Anything here that changes *which serial bytes get sent when* is
a physical change to when the laser can fire or stand down. Verified: the only cut with that reach
is the `>lpm` parser (trap #4). Everything else is display/dead code.

- **B1. v1 "rejected:" sniff — [0], confirmed dead, 3-file commit.** Only ERROR producers are
  "unknown command"/"GUI exception"; every rejection is structured REJECTED. But a **live test
  asserts the sniff** (`test_zmq_v2_protocol.py:253` + its `value==994` mock branch) and
  `_setLampMode`'s docstring still documents the old pattern — all three must go together or the
  suite red-lines / the pattern re-seeds. Re-verify if any pre-rebuild branch (which still has
  ERROR+rejected producers) ever merges.
- **B2. `_prepMode` prologue helper — DISPUTED, recommend skip.** The prologues differ in 4 places
  (mode value, setter, and three operator-visible strings), `warmupActive = True` must stay BEFORE
  the standby send (its position is load-bearing), and both callers deliberately ignore the setter's
  return to trust the hardware readback — a "cleanup" that normalizes any of that changes arm/warmup
  semantics. ~12 lines saved on the lamp-arming path is a bad trade. **Side-find for /code-review**:
  `_setLampMode`'s parse-failure branch returns before refreshing the cached mode; `startLaser`
  verifies against that stale cache — an unparseable `>lpm` reply can still let the arm sequence
  proceed (lamps→shutter→Q-switch). Same class as the audit's `_remoteSetVoltage` finding.
- **B3. `updateAllStatusIndicators` table — [0], confirmed.** Pure rendering; interlock chain
  (:719-750: shutter⇐lamps, Q-switch⇐lamps+shutter, single-pulse⇐…) verified outside the table's
  scope. Keep the table strictly above :719.
- **B4. `btnContainer` — DISPUTED: the "zero-lasers bug" does not exist.** Empirically replicated
  the layout choreography 10/10 configurations incl. zero-lasers-at-start: `itemAtPosition` returns
  the right widget every time. Cut it as robustness/readability [0] — but don't book it as a bug
  fix, and don't let that skip the GUI eyeball.
- **B5. Misc — deletions [0] confirmed; `>lpm` unification is trap #4.** Commented sliders reference
  widgets absent from the .ui; `proposedEnergy` write-only; unused imports exact (note
  `concurrent.futures` is unused in the *controller* file but LIVE in HugeSkyController.pyw:141,145 —
  scope the cut). The `>lpm`/`>qsm` parsers: keep strict-parse semantics (mangled reply → ignore,
  state untouched). Decide together with B6 (same fallback path).
- **B6. `_query()`/`getState()` tables (Tier 2) — gates re-verified accurate.** Nonsense-mode→standby
  fallbacks exist in exactly the two mode-query methods; `_stateLock` is non-reentrant and today
  never held across Qt setters (a generic helper that setValue's inside the lock can deadlock the
  GUI via the spinbox→setVoltage→getVoltage-on-ZMQ-thread cycle); conftest mocks the six `update_*`
  by name (test churn). Physics: get this wrong and the GUI freezes — the operator loses laser
  control mid-session.
- **B7. Green-echo into `_sendCommand` (Tier 2) — [E], bigger than stated.** Semantics are already
  mixed (~13 sites echo on bytes-returned, ~9 after parse); centralizing flips the 9. After the
  change, green stops meaning "this value is now trusted" for voltage/energy/temperature reads —
  a garbage reply prints a green echo of the garbage before the orange parse error. Two omissions:
  the hidden safety standbys (:668,:686) would START echoing (arguably good — surfaces an invisible
  `>s`), and the echo must not fire on the `_handleDisconnect` paths. Accept knowingly + document,
  or skip.

## Tier 1 — GUIs/HF_Locking (audit lines 79–81 + Tier-2 133–135)

Physics framing: the wavemeter GUI holds the spectroscopy/cooling lasers on frequency (WS7 readout →
PID → DAC). **Re-verified with fresh evidence: no cut touches lock acquisition (5-consecutive rule,
`lock_tolerance()`, 60 s timeout), the PID write path, `get_frequency_num`, or DLL call semantics** —
the "zero DLL-semantics change" framing holds because `wlmData.py` declares argtypes for all four
wrapped calls (ctypes coerces the by-hand ints to the wrapper's exact marshalling). Lock physics is
untouched by H1–H6.

- **H1. verbose blocks + StatusString ladder + `get_frequency` + `get_all_status` — [0], confirmed.**
  `verbose` is assigned exactly once (`= False`, no env/config path); the StatusString ladder is dead
  computation executed on EVERY per-channel poll — deleting it marginally lightens the ~40 Hz hot
  path. `get_frequency` zero callers incl. autospec (specs off the class; no test touches it);
  `get_all_status` dead sibling of the live `get_all_measurements`.
- **H2. Registry loops + wrapper reuse + `Version_*` — [0], byte-equivalence VERIFIED not assumed.**
  The one real trap: `read_live_state`'s try/except is **per-setting**; a table refactor that hoists
  it to per-registry makes one DLL hiccup silently drop ~20 settings for that port → `compare_configs`
  under-reports diffs → **the restore dialog silently mis-restores PID gains** (wrong lock dynamics:
  sluggish or oscillating lock). Keep the exception granularity; build the bound-method table inside
  the function (`wlm` is a parameter). `set_channel_assignment` via the wrapper now returns an int —
  its one caller ignores results, fine. Audit's own process note (verify against a real
  `pid_config.json` diff — file confirmed live, 2026-08-10) is the right gate.
- **H3. `_target_screen()` + `(cb, saved)` + `FREQ_PAD_FRAC` + comment — [0], confirmed.**
  `FREQ_PAD_FRAC` is defined and never read (frequency plot pads via `_nice_y_range` min-span) —
  deleting it changes no pixel of the lock display. The helper preserves match-by-name QScreen
  (house rule). The "display_wide" comment is actively FALSE (numpy is used 7× inside the 33 ms
  autoscale path) — delete the comment, keep the import.
- **H4. `_voltage_dirty` (Tier 2) — [0], cut the PAIR or neither.** Write-only confirmed; the
  press→defocus race story (cbd32d9) checks out; the gate's "leave a one-line pointer" is already
  satisfied by the existing 4-line comment. Audit missed the twin: `_voltage_pending_until` is
  equally write-only. Net ~8 lines, not 12.
- **H5. `restore_settings` table + slot merge (Tier 2) — right conclusion, corrected reason.** The
  two `@pyqtSlot`s are connected with explicit `QueuedConnection` (not AutoConnection); the real
  invariant is that the WavemeterWorker thread owns ALL runtime DLL I/O — any merge that shortens
  the path to a direct GUI-thread call risks cross-port data corruption in the DLL. Keep both bound
  entry points; collapse only the 4-branch registry chain, bundled with H2.
- **H6. config.py logging→print (Tier 2) — [D], two changes not one.** Warnings/errors move
  stderr→stdout AND the 4 currently-silent `logger.info` lines (config save/load) become visible.
  Operator impact ≈ nil (console launch, same window); write the commit message honestly.

## Tier 1 — Backend forks (audit lines 85–91 + Tier-2 117, 125–128)

Physics framing: this is the shot state machine — the code path between "queue a shot" and "data
on disk". K1–K7 are demo harnesses, husks, and write-only attributes off that path: zero physics.
The Tier-2 items (K8–K12) ARE the shot path; three of them change error-path behavior by design and
carry the audit's own ≥3-shot + mid-queue-abort validation gate. The cluster's real danger is
applier precision, not physics — three traps sit adjacent to load-bearing lines.

- **K1. Plot demo harnesses — [0], confirmed** (no external refs; keep `threading` in analoginput;
  `Instance`/`KillInstance` have live callers elsewhere — K1 doesn't orphan them).
- **K2. `_update_state_label` husk — [0], confirmed** (body pass, all call sites commented; the
  commented body is the only prose mapping mode ints 16/32 to names — trivia loss only).
- **K3. `setTopLevelWindow` + 'focus' — [0], confirmed** (all nine parent→child `to_child.put`
  sites send literal cmds; nothing sends 'focus'; delete `:141-148`, the elif AND the method).
- **K4a. `last_requested_state` property→attr — [0] with trap:** `__init__` sets
  `self._last_requested_state = None`; delete the property without renaming that line and the FIRST
  state-machine event AttributeErrors → mainloop thread dies → **every tab red, no shots**. Rename
  in the same edit. No external readers; all access already under the queue's own lock.
- **K4b. BLACS_DIR fallback — [0], confirmed decisively** (five modules already do the bare import;
  if it could fail, BLACS would be dead before the fallback mattered).
- **K4c. Registry spec-guard — leave it.** Behavior-neutral to cut, but it landed 3 days before the
  audit in the Py3.12 compat fix — not worth re-litigating a fresh commit for 4 lines.
- **K5a-c. KillInstance guard / `Legend.items` / `plot_win = None` — [0], confirmed** (zprocess
  Process.__init__ verified side-effect-free; C++ parenting keeps widgets alive without the Python
  list; no read between init and reassignment).
- **K5d. `res = {}` — [0], HIGHEST APPLIER RISK.** It sits **directly below** the d1cf0b5
  queue-deadlock fix line `self._final_values = {}` — identical shape, adjacent lines. Deleting the
  wrong one re-opens the "None.update() → fatal tab → orphaned-wait queue deadlock" failure. Match
  the literal string `res = {}`, never a line number; diff-check `_final_values` survives.
- **K5e. `qt_mainloop_instantiated` / `queue_inmain` — [0] with TWO traps the audit half-states.**
  (i) The Qt-startup barrier is the **`@inmain_decorator(True)` decorator**, not the method body —
  `pass` body WITH decorator = correct barrier; body without decorator = silent startup race (tab
  hangs with no error). Keep the decorator, empty the body. (ii) **Name collision**: the write-only
  flag is `StateQueue.qt_mainloop_instantiated` (:80,:86); `Tab.qt_mainloop_instantiated`
  (:308,:786,:789) is a DIFFERENT, live attribute read as the barrier's gate — a name-based sweep
  kills tab startup.
- **K6. NI_DAQmx `DataReceiver` attrs + imports — [0], confirmed** (the reads live only in
  IMAQdxCamera's own class; NI_DAQmx's are a copy-paste with no reader; `inmain_decorator` stays).
- **K7. `_reset_data_socket` dedup — [0] with 3 ordered preconditions:** `_zmq_context` and
  `_data_socket_addr` assigned first, then `self.data_socket = None`, then the call — get it wrong
  and the AI worker never starts (**that NI card's tab dead, every AI channel on it dark** until
  fixed). Net ~2 lines, not ~5. Validate with a BLACS restart + NI tab check, not a shot.
- **K8. Tab template-method collapse (Tier 2) — DISPUTED, redesign the design first.** The ordering
  gate (`_init_subscriber_registry()` before `super().__init__()`, test-pinned) is real. But 2 of 3
  claimed divergences are false (BigSky DOES use DynamicStackedWidget; `_monitor_labels` exists in
  all three tabs) — only LaserLock's skipped AO-for-monitor creation holds. And the collapse itself
  creates a NEW instance of the 2026-05-26 failure class: the base `initialise_GUI` re-assigns
  `_extra_topics`/`_pubsub_monitor_cache` mid-flow, so any subclass registering topics before its
  `super().initialise_GUI()` call gets them silently wiped — invisible today only because no
  subclass calls super at all, and the existing test can't catch it. Also collides with item F
  (same lines). Physics if botched: a tab that silently stops receiving its GUI's PUB-SUB stream —
  stale panel numbers with no error.
- **K9. Queue yield collapse (Tier 2) — gates right, mechanism corrected.** A bare `yield` does NOT
  flip to old_worker_flow — it **abandons the generator**: no worker contacted, post-yield body never
  runs, silent per-shot no-op. Additional exclusions the audit missed: `yield None` at
  `device_base_class.py:807` is LIVE (the post_experiment back-compat branch, on the queued-shot
  path); `check_main_first` is True at 3 sites / False at 4 — a single-default helper silently
  changes whether a failed primary worker fail-fasts the buffered transition. Batch + 3-shot+abort
  validation stands.
- **K10. `set_status` removal (Tier 2) — DISPUTED: gate incomplete.** The audit lists cycle_time
  `:104,:116` but misses **`:99` `get_status()`** — in `do_delay`, invoked per shot via
  `science_starting`. Applied as gated, the moment anyone sets `cycle_time = True` in labconfig the
  queue AttributeErrors **mid-run between programming and fire** → queue stalls. Fix all three lines
  or leave both methods. (Verified: `set_status` body is ALREADY pass; the `get_status()=="Idle"`
  read at :584 is permanently False against the .ui default text — the "meaningless read" claim is
  exactly right, zero log delta.)
- **K11. `create_subset_widgets` collapse (Tier 2) — [0], confirmed** (both callers 3-unpack; the
  4-tuple branch is already a guaranteed ValueError; `_image` only ever populated by LightCrafterDMD,
  which never calls this). Sequence with the dead-twin deletion (item 2) — the twin holds the
  second caller.
- **K12. `queued_experiments` try/except (Tier 2) — [E], both sides understated.** Today an
  exception in `has_next_file()` at quit leaves devices in MODE_POST_EXP holding buffered state (the
  known stranding class — arguably the latent bug); after the cut it surfaces as a traceback popup +
  silently-paused queue (NOT "queue paused" text — set_status is already a no-op). The cut arguably
  *fixes* a bug at the cost of a recurring quit-time traceback that log triage will flag. Decide
  with eyes open; batch with K9/K10.

## Tier 2 — repo/sequence items (audit lines 113–119, 131–132, 98, 96–97 partial)

Physics framing: legacy sequences and backup connection tables are archives of past experimental
configurations (BaF-era hardware: COM12 PrawnBlaster, NI_6363, photon-counting config). None can
run against today's apparatus; the questions are provenance policy, not physics.

- **T1. lyman29 trees — safe with corrections.** `test.py` IS a byte-dup of `analysis_multishot.py`;
  **`benchmarking.py` is unique** (no duplicate — half the stated justification is wrong; the cut
  still stands on dead-code grounds). Notebooks name two sequences as strings, zero imports.
  **T1↔T3 is a hard dependency, not sequencing**: all three legacy sequences
  `from labscriptlib.lyman29.subsequences... import *` — if T3 is rejected, T1 cannot proceed.
- **T2. repo-root tests/ spikes — [0], confirmed** (five files, 798 lines exact; exactly 4 citing
  docs; the empirical-test-proposal doc embeds the full source listings, so the A1–A15 evidence
  survives the delete).
- **T3. Legacy sequences — conclusion defensible, rationale CIRCULAR.** "Verified non-compiling"
  traces to the files' own header comment (added by a3316ae "label stale files") — a self-citation.
  Statically they are self-contained (own inline PrawnBlaster/NI CT) and import-clean; the one
  provable static failure is `BaF_scanning`'s odd DO-child count (2 explicit + 1 camera trigger →
  `_check_even_children` raises). Either run ONE RunManager compile before deleting, or restate the
  rationale as "BaF-era hardware, CT-incompatible at the BLACS boundary". sequences.md amendment
  gate confirmed verbatim ("don't archive or delete") and must land same commit.
- **T4. Backup CTs — [0], confirmed.** Tracked & clean; **recovery hash for all three:
  `a3316aea856160f244ff96e4537df85490558ea4`** (`git show a3316aea:<path>`). open_cell2 correctly
  excluded (it's the deliberate fc810b7 swap-back — Tier 3).
- **T5. old_environment.yml ×2 — gate under-specified; lazy fix available.** CLAUDE.md's 3 pins ≠
  the 115 build-pinned packages. `old_fresh_environment.yml` (13 lines, python==3.11.9 + pins) IS
  the artifact the gate wants: **keep it (or move to docs/), delete only the 119-line export.**
- **T6. lessons_with_shafin — [0], scope leak.** Not lyse-registered. The PI sign-off must cover the
  WHOLE onboarding set: the Tier-1 `main_experiment_control/` delete silently takes the sequence
  half (`sequences/lessons_with_shafin.py`, `dummy_benchmarking.py`, 2 globals .h5) with it.
- **T7. Launch Labscript.bat cosmetics — [0] with 2 traps.** `%progress%` is WRITTEN by detector
  lines 53-56 (only the bar lines 58-62 are cosmetic); the `:SUCCESS`/`:FAIL` labels are jump
  targets (gut the echo text, keep the labels; `:FAIL`'s `pause` is functional); `timeout /t 1` at
  :78 is the loop's CLOCK (removing it = instant false FAIL); `timeout /t 2` at :97 is safe to drop.
- **T8. backup-memory.sh — [0], confirmed; snapshot near-worthless** (9 files vs ~28 live, 3 months
  stale). One pre-delete check: `memory-backup/device-internals.md` (9,179 B) vs live (298 B) —
  confirm the content lives in `docs/device-internals.md` before deleting the backup.
- **T9. pre-push TEST_PATHS — STALE (~70% superseded by 8134dba)** + the reinstall claim refuted
  (see Headline). Residual: flatten the always-true external_gui_lib conditional + its stale
  comment (~5 lines).
- **Graphify postmerge_fix.py — covered under analysislib section.**

## Tier 1 — analysislib smalls + tooling (audit lines 95–97, 102, 107 + Tier-2 136–139)

Physics framing: this is the code that turns raw traces and camera frames into the numbers the lab
actually quotes — optical depths, integrated fluorescence, scan curves. A wrong cut here is worse
than a crash: it changes reported physics silently. The verification swept all 56 notebooks on disk
(17 gitignored — invisible to any tracked-file audit) and proved the lyse flag semantics from lyse
source: **flag 0 = unchecked = lyse does not run it; `analysis.py` is the ONLY active routine**
(even `analysis_multishot.py` is at flag 0 — every "re-run it after" gate first requires ticking
the routine's Active box).

- **Y15(1). `_compute_od` → `filtering.process_trace` — REJECT. [P] Silent physics regression,
  the headline finding of this review.** The two functions are different math: `_compute_od`
  detrends by *slope only* (keeps the intercept — `I0 = mean(pre-trigger)` stays the real
  transmitted intensity), then computes `-log(signal/I0)` — a ratio; 5.0 ms fit tail.
  `process_trace` subtracts slope AND intercept and then the pre-trigger mean — baseline driven
  to ≈0; no log, no ratio; 1.0 ms tail. Substituting it makes `I0 ≈ 0`, `-log(0/0)` → non-finite →
  the existing clamp writes **OD = 0.0 everywhere, with no exception raised**. Every absorption
  measurement analyzed after that cut would read zero optical depth and nothing would error.
- **Y15(2). Pre-trigger algebra → `-0.01·time_ms[-1]` — [0] with 2 nits.** Algebraically exact
  (the `n_pts/fs` factors cancel), but: (i) the current `else 1e6` degenerate-input guard yields a
  sign-flipped offset under the proposal; (ii) the adjacent operator diagnostic print still needs
  `n_pts`/`fs`, so the line saving mostly evaporates. Line-neutral; fine if both handled.
- **Y15(3). Stored-scans double-write — [0]**: cut the write (`:482-483`) and its read-back
  (`scan_explorer_widgets.py:508-509`) together, or a clear-handler survives for a dict nobody writes.
- **Y15(4). `_load_summary_html` duplication — [0], confirmed** (recomputes the identical OD-range
  and fluorescence-peak numbers; genuinely behavior-neutral given Y5).
- **Y14. `ScanAnalysis.single_trace()` — [0], confirmed dead**, with one commented reference in the
  *tracked live explorer notebook* (`Closed_cell_explorer.ipynb` cell 17) — one keystroke from
  active. Delete that commented line in the same commit or the uncomment becomes an AttributeError.
- **Y1. opencell Front/Cell → loop — [0] numerically** (identical masks and padding), but the loop
  must carry per-axis xlabel (only Cell has one today) or the shared-x layout changes. Flag-0 gate:
  tick Active before the verification re-run.
- **Y2. Multishot commented blocks + `image_data_nuvu`/`count` — [0]**, and the commented
  fluorescence-image feature they serve is **already broken** (`count` is never incremented →
  ZeroDivisionError on uncomment) — delete the whole cluster, it is not dormant, it is dead.
- **Y3. Axis-styling helper — rescope.** ~10 clusters, not 5, and the params are NOT identical
  (legend presence/location/fontsize vary; ylabel is conditional first-column-only at 2 sites).
  A uniform helper silently changes plot furniture. Parameterize or skip.
- **Y4. Spectroscopy branch merge — NOT VERIFIED.** The branches carry per-signal integration signs
  (`sign=-1` fluorescence vs `+1` OD). Treat as numeric; do not apply without a line-by-line diff.
- **Y5/Y6. `_print_summary` + StringIO ×4 — [0], confirmed** (all four buffers written, never read;
  the operator sees the same numbers via the HTML panel; `ScanAnalysis` has zero notebook callers
  that would escape the wrapper).
- **Y7. `_MODULE_STATE` fallback — audit inverted the defect.** The branch is *reachable* (any
  non-IPython import) and already broken (missing the `'stored'` key its consumers assume).
  Delete the fallback AND the `ip is None` branch together, or fix the dict — not half.
- **Y8. `_avg_integrate` → tuple — line-neutral, skip.** Four callers each gain a line; the error
  it propagates is the physics error bar (`sqrt(sum σ²)·dt`) — a mis-wired tuple silently swaps
  value and sigma.
- **Y9/Y10. Import hoists (ipywidgets stays local — verified it's the only one), `sosfreqz`,
  `YAG_DELAY`, NI_SCOPE argparse — [0], confirmed.** `YAG_DELAY` verified NOT part of the Tier-3
  "about to be needed" NI_SCOPE snippet; the string `'YAG_DELAY'` in the explorer's globals-name
  set is unrelated — don't sweep it.
- **Y11. Ch0/Ch1 fallback + `_extract_time_value` — verify against one recent h5 first.** The two
  cut together consistently and have zero notebook refs, but "layouts that no longer exist" was
  reasoned from code, not proven against a real shot file. `_resolve_fs_hz` keep confirmed separate.
- **Y12. lyman29/analysis.py dead blocks — NOT VERIFIED** (file not opened; falls under the
  lyman29 Tier-2 gate anyway).
- **Y13. `jim_DIO_acquire.py` 1-126 — [0], confirmed** pure comment (zero non-blank stripped lines).
- **Y16. `group_and_subtract`/`baseline_correct_batch` — gate confirmed, exactly one notebook**
  (`archive/Closed_cell_03_05_2026.ipynb` cell 1, gitignored → invisible to git) — and the import
  statement is COMBINED with the must-keep `integrate_window`, so the whole cell dies, not two names.
- **Y17. `shot_setup.py` — [0], both claims verified** (10 boilerplate copies → 3 after the
  prerequisite deletions; sys.path claim proven by `analysis.py`'s bare sibling import running in
  production). Ordering is load-bearing: deletions FIRST, then build the helper (3 migrations, not 10).
- **Y18. IMAQdx dedup — conclusion stands, cited evidence wrong.** All three md5s differ; the two
  analysislib copies are identical only modulo CRLF/LF. Re-verify with `diff --strip-trailing-cr`.
- **Y19. `_GRID_ON`/`set_grid` → rcParams — REJECT the internals swap. [D→P]** `plt.grid(True)` is
  an explicit post-plot call on the current axes; `rcParams['axes.grid']` is global and
  creation-time — the swap leaks the NI_SCOPE grid toggle into every other plot in the kernel and
  stops affecting already-created axes. `set_grid` is live-called from `Testing_5922.ipynb`.
  Keep shim AND internals as-is.
- **Y20. graphify `postmerge_fix.py` — partially STALE** (8134dba added a Counter branch post-audit).
  `lru_cache` swap clean; the orphan-stub pass is output-equivalent to delete BUT lines :220-221
  feed a REFRESH.md-facing report metric — keep them; the real win is hoisting the per-element
  `set(orphaned)` rebuild.

## Tier 3 — REJECTED items

No change: the do-not-cut table stands. Nothing in this review weakens any Tier-3 rejection; several
verifications (BigSky safety guards, HF autoscale reasoning, `Closed_cell_scan.py` as the only
scan-wired sequence) were incidentally re-corroborated. **Never apply Tier 3.**

## Cross-item ordering constraints (apply in this order within each repo)

1. Push rastering/HF mains → remove stale worktrees (item 5 + ui-redesign) → then any HF/rastering edits.
2. Item F (monitor surface) **before** M (which then drops) and coordinated with K8 (same lines).
3. R7 before R2 (bare-except sites); rebase/merge `rastering-atomic-xy` before R5.
4. Item 2 (dead twin) with K11's second caller in mind; item 5 before item 6 (HF CLAUDE.md copies).
5. D + J land together (conftest ↔ test_zmq_v2 self-runner/docstring).
6. B5(>lpm) and B6 are one decision (same fallback path).
7. K9 + K10 + K12 batch on one branch → ≥3-shot queue + mid-queue abort validation (audit gate confirmed).
8. T3 decides T1; sequences.md amendment in the same commit as any sequence/CT deletion.
9. Y17: analysislib deletions FIRST, then build `shot_setup.py` (3 migrations, not 10); tick lyse
   Active boxes before any "re-run to verify" gate (only `analysis.py` is checked today).
10. Y14: delete the commented `single_trace` line in the live explorer notebook in the same commit
    as the method.

## Corrections to carry back into the audit doc

- Item 12 → split: `git rm` space file; TRUNCATE NI_SCOPE `__init__.py` (never delete).
- Nuvu dead-surface list → remove `millisecond_to_fps` (live) or expand to the full `__real_fps` chain.
- R1 → rewrite against the current .ui (32-name subset, 3 stub-required keeps).
- R6 `_move_reply` → re-file to raster_controller.py; `_user_home_both` caveat → remove (no collision).
- R9(a) → move to "don't" (unit-label regression).
- B4 → reclassify as cleanup (bug disproven empirically).
- B5 `>lpm` → move out of "misc confirmed" into gated, with the standby-reach delta stated.
- K10 → add cycle_time `:99` to the gate.
- K5e → "keep the decorator, empty the body"; name-collision warning.
- Line 201 process note (per-worktree hook reinstall) → strike; one `cp` suffices.
- T9 → mark superseded by 8134dba except the 3-line conditional flatten.
- T3 → replace "verified non-compiling" with the honest rationale (or run one compile).
- Y15(1) `_compute_od` reuse → strike from the audit (REJECT — silent OD collapse).
- Y19 `_GRID_ON` rcParams swap → strike the internals swap (global/creation-time ≠ per-axes/post-plot);
  keep shim and internals.
- Y7 → reframe: fallback is reachable-but-broken, not unreachable; cut both halves or fix the dict.
- Y3 → "identical params" is false (~10 clusters, varying legend/fontsize/conditional ylabels).
- Y16 → note the archive notebook's import is combined with must-keep `integrate_window`.
- Y18 → replace md5 evidence with `diff --strip-trailing-cr` (CRLF/LF).
- Flag-0 note → applies to `analysis_multishot.py` too; `analysis.py` is the only Active routine.
- Adjacent-findings list: #2 (flip checkboxes) → FIXED by redesign; add B2's `_setLampMode`
  stale-cache arm-path gap as a new /code-review item alongside #1.

---
*Review run 2026-08-14 by 7 opus verification passes (2 duplicated for corroboration) orchestrated
from the main session; every verdict above is backed by file:line evidence or an executed check in
the agents' reports. Nothing applied.*
