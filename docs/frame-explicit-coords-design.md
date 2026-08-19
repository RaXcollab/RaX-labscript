# Frame-Explicit Coordinate Communication (BLACS ↔ Rastering GUI)

Status: DRAFT for review — not implemented (2026-08-04, rev 2 after review)

Target design for the "Units pass", open item (1) under *Rastering edge-coordinate hardening*
(`.claude/open-items.md`). Decided principles (`.claude/session-handoff-2026-08-04-raster-echo-chain.md`
§"Units direction"): motor units are **FIXED** (Z912 travel `0–12 mm`, stable across recalibrations);
pixel units **vary with every re-fit**, so no CT bound may ever be tied to one calibration. The wire
carries pixel OR motor coordinates, **frame-tagged**; once motor-frame comms exist, CT channels declare
motor units with fixed `(0, 12)` limits.

**Already landed** on `feat/open-items-batch` (rastering `202004e`, `5fede41`; parent `e517c86`,
`d66c782`, `05a3acd`) — this design builds on it and must not undo it:

- compound `laser_raster_xy` PROGRAM_VALUE with optional `args["frame"]`, tokens `"pixel"`/`"motor"`,
  default `"pixel"`, typed **`invalid_frame`** on anything else;
- `_handle_check` `:606`/`:608` and publisher `:2285` motor fallbacks **deleted** —
  `laser_raster_{x,y}_coord_monitor` are now target-frame only, with an in-code comment forbidding
  motor-frame values on them;
- `raster_point_meta` emits `"frame"`, and `RASTER_META_KEYS` forwards it into the h5.

Protocol claims are against `userlib/external_gui_lib/zmq_v2.py` on master today.

## (a) HELLO extension: per-connection frame/units declaration

Today `_handle_hello` (`zmq_v2.py:355-363`) emits `protocol_version`, `server`, `capabilities`, and — only
when `ADVERTISED_CONNECTIONS` is set — `connections`; the client (`RemoteControl/blacs_workers.py:232-234`)
**logs** the reply and stores nothing. Add one optional top-level reply key, `frames`, following the
`connections` precedent (optional, additive, hint-not-contract):

```json
{"v": 2, "id": 0, "status": "SUCCESS", "protocol_version": 2, "server": "RasteringGUI",
 "capabilities": ["heartbeat", "monitors"], "calibration_id": "px2mm:9f3c1a2b",
 "frames": {"laser_raster_x_coord": {"default": "pixel", "supported": ["motor", "pixel"],
                                     "units": {"motor": "mm", "pixel": "px"},
                                     "motor_limits": [0.0, 12.0]}}}
```

`default` = frame assumed when `args["frame"]` is absent — declared `"pixel"` to match the landed GUI
default, so declaring it changes nothing. `supported` = accepted tokens; `units` = label per frame, never
a bound; `motor_limits` = OPTIONAL fixed travel, cross-check target only (pixel ranges deliberately NOT
advertised). `calibration_id` = `"px2mm:" + sha1(json(M) + json(b))[:8]`, absent when uncalibrated —
identity only.

**One addition in `zmq_v2.py`** — a `hello_extra()` hook returning `{}`, merged last into `_handle_hello`'s
`extra` dict; rastering returns `{"frames": ..., "calibration_id": ...}`. No `DECLARED_FRAMES` class
attribute: `ADVERTISED_CONNECTIONS` earns a static attr because three GUIs set it, whereas `frames` has
one producer and one of its two keys is runtime state. **`capabilities` is NOT touched** — pinned by
`CANONICAL_CAPABILITIES` (`zmq_v2.py:47`); a new string forces the Q3 two-step PR for no gain, and the
presence of `frames` is its own discovery flag.

**Precedence — declaration never gates what BLACS sends.** The CT is the only authority on a request's
frame: BLACS sends `args["frame"]` from the CT declaration whenever that declaration is not `"native"`,
regardless of whether the server advertised `frames`. A non-declaring server either honours it or rejects
it per-request (`invalid_frame`); a mismatch against an advertised `supported` list is logged once at
HELLO and nothing more (Q1: "advertisement is a hint, not a contract"). `frames` absent → client stores
`{}` → cross-check skipped; zero change in LaserLock/BigSky. Client side, `connect_to_remote` gains two
lines storing `response.get("frames") or {}` and `response.get("calibration_id")`.

## (b) Frame-tagged PROGRAM_VALUE / CHECK_VALUE

`frame` rides in the existing `args` dict — no envelope change; `encode_request` forwards `args` verbatim
(`zmq_v2.py:187-202`), so a write is `args: {"wait_for_lock": false, "frame": "motor"}`. **BLACS always
sends `frame` explicitly** for non-`"native"` channels, exactly as it now always sends `wait_for_lock`
(§1.2 footnote, 2026-07-07: "absence is never interpreted via server-side defaults"); server-side
defaulting exists only for hand-driven debug clients. Every reply echoes the `frame` actually executed
plus the two provenance keys §(d) stamps (`calibration_status`, `calibration_id`).

Routing inside `_RasteringV2Server._handle_program` (`raster_controller.py:381`) — the `laser_raster_xy`
rows landed in `202004e`; the two single-axis motor rows are new:

| connection | frame | executes |
|---|---|---|
| `laser_raster_x_coord` / `_y_coord` | `pixel` | `request_move_x` / `request_move_y` (today's path, `MOVE_X_ONLY`) |
| `laser_raster_x_coord` / `_y_coord` | `motor` | `request_move_motor_axis("X"/"Y", v)` (`:855`, `MOVE_MOTOR_X_ONLY`) |
| `laser_raster_xy` | `pixel` | `request_move_target` (`:780`) — one `target_to_motor`, one `clamp_to_bounds`, one bounds check |
| `laser_raster_xy` | `motor` | `request_move_motor` (`:836`, `MOVE_MOTOR`) |

Anything else → the landed typed `ERROR`, `code: "invalid_frame"`, `retryable: false` (reuse it; do **not**
add a second code for the same condition). Extend its message to name the connection's `supported` list.
Asymmetry to document, not fix: `clamp_to_bounds` (`MOTOR_EDGE_CLAMP_MM = 0.010`) applies only on the
**pixel** path (`:1978`) — a motor-frame request is already in the bound's own units, so an out-of-travel
value is a real operator error and rejects (`:1896`).

`CHECK_VALUE` takes the same `args["frame"]` and **must** echo `frame`: `"motor"` → `_last_motor_xy`
component (valid uncalibrated); `"pixel"` → `_last_target_xy` component, and when None the landed
`position_not_initialized` refusal (`:618-623`). Never a motor number wearing a pixel label.

**PUB: add, never re-label.** `5fede41` pinned `laser_raster_{x,y}_coord_monitor` to the target cache with
an explicit comment against motor-frame values there; repointing them at `_last_motor_xy` would flip a
live topic *and* the front-panel echo chain *and* the `Raster_*_Monitor` CT units in one step. Publish a
new pair instead:

| topic | frame | when |
|---|---|---|
| `laser_raster_{x,y}_coord_monitor` (existing, unchanged) | target: px calibrated, mm passthrough | whenever `_last_target_xy` is set |
| `laser_raster_{x,y}_mm_monitor` (**new**) | motor mm, unambiguous | whenever `_last_motor_xy` is set |
| `calibration_status` (existing), `calibration_id` (**new**) | — | ~1 Hz |

Both new coord topics also answer `CHECK_VALUE` — a CT monitor is polled by `check_status`, not only
PUB-read — so `_MONITOR_X`/`_MONITOR_Y` (`raster_controller.py:350-351`) each gain the `_mm_monitor` name,
and `_handle_check` picks the cache from the *connection* (not from `args["frame"]`) for those two.

## (c) Connection-table migration

Today (`connection_table.py:106-142`) all four raster children are `units="mm", limits=(0, 25.0)` while
the wire carries **pixel-frame target coordinates**: wrong frame label, and `25.0` matches neither travel
(`12`) nor any pixel range.

**Not a compile blocker.** All three sequences call `Raster_X.constant(RASTER_X)`
(`sequences/Open_cell.py:26-27`, `Closed_cell.py:24-25`, `Closed_cell_scan.py:25-26`, all commented out)
and the globals are `RASTER_X = 2.12667`, `RASTER_Y = 1.07629` (`Globals/BaF_globals.h5`, read
2026-08-04) — inside `(0, 25)` *and* `(0, 12)`, so uncommenting compiles both before and after the
migration. The `limits` → `LabscriptError` path is real (`RemoteAnalogOut` forwards `limits` into
`StaticAnalogQuantity`, `labscript_devices.py:159-166`) but **unarmed**; it fires only on a genuinely
pixel-scaled value (e.g. `110`). Earlier notes calling this a latent compile blocker are wrong; corrected
in `.claude/open-items.md` too.

```python
RemoteAnalogOut(name='Raster_X', parent_device=RasteringGUI, connection="laser_raster_x_coord",
                units="mm", limits=(0, 12.0), frame="motor", decimals=4, step_size=0.001)
# Raster_Y identical. Raster_{X,Y}_Monitor -> connection="laser_raster_{x,y}_mm_monitor", units="mm",
#   limits=(0, 12.0), frame="motor".  Optional new target-frame monitors on the EXISTING topics:
RemoteAnalogMonitor(name='Raster_X_Px_Monitor', parent_device=RasteringGUI, decimals=1,
                    connection="laser_raster_x_coord_monitor", units="px", limits=(0, np.inf), frame="pixel")
```

`limits=(0, np.inf)` on pixel monitors is deliberate: the only calibration-independent pixel bound is "no
bound". Plumbing for the new `frame` kwarg — **5 edits, not 3**:

1. `labscript_devices.py` — add `"frame"` to the `connection_table_properties` list of `RemoteAnalogOut`
   (`:124-131`) and `RemoteAnalogMonitor` (`:179-186`), **and** add `frame="native"` as a real `__init__`
   parameter on both. `set_passed_properties` reads named parameters only; without the parameter
   `frame=...` falls into `**kwargs` and reaches `StaticAnalogQuantity.__init__` as a `TypeError`.
   `"native"` = "one unnamed frame" (what LaserLock/BigSky channels keep).
2. `RemoteControl/blacs_tabs.py` — alongside `AO_prop` built from `dev._properties` (`:161-170`), collect
   `child_frames = {dev.parent_port: cp.get("frame", "native")}` over output **and** monitor children;
   pass it in the `create_worker` kwargs (`:244-259`).
3. `RemoteControl/blacs_workers.py` — `RemoteCommunication.program_value` gains a `frame=None` kwarg,
   adding `"frame": frame` to args when not None. It hard-codes `args = {"wait_for_lock": ...}` today
   (`:361`) and is the **only** place output `args` is ever built, so nothing else can inject the key.
4. Same file — `check_remote_value` gains `frame=None`; it passes `args=None` today (`:387`).
5. Same file — `program_manual` / `transition_to_buffered` / the read pollers pass
   `frame=self.child_frames.get(connection)`, mapping `"native"` → `None` (key omitted; frame-less
   devices byte-identical to today). `RasteringDevice/blacs_workers.py` drops its "we rely on the default
   and send no frame tag" comment and passes the CT frame through.

Sequence-side consequence: `RASTER_X`/`RASTER_Y` become **motor mm in 0–12** by declaration — that is the
point; a shot's requested position then survives recalibration. A sequence wanting pixel targeting uses a
pixel-frame channel and accepts that its numbers mean nothing after a re-fit. Verify at migration: compile
with the raster lines **uncommented**, then restart BLACS and confirm the restored front-panel value (saved
under the old `(0, 25)` range) lands inside `(0, 12)` rather than being clipped to 12.

## (d) h5 provenance

Today `/data/{dev}/monitor_values/{initial,final}_monitor_values` (`RemoteControl/blacs_workers.py:757-771`)
is a bare float64 table built from `dict(self._pubsub_cache)` (`:719`, `:736`): an uncalibrated mm shot and
a calibrated px shot are byte-indistinguishable. Stamp attrs on the `monitor_values` **group**, in
`post_experiment` (never earlier — `/data` is the queue manager's "shot has run" marker):

| attr | source | example |
|---|---|---|
| `frames` | JSON of `{connection: frame}` from `self.child_frames` — CT declaration, never read off the wire | `{"laser_raster_x_mm_monitor": "motor", "laser_raster_x_coord_monitor": "pixel"}` |
| `calibration_status` | last `CHECK_VALUE` reply extra | `"calibrated"` |
| `calibration_id` | last `CHECK_VALUE` reply extra | `"px2mm:9f3c1a2b"` |

The two runtime strings come from **reply extras on the existing 5 s output poll**: `check_remote_values`
(`:589`) walks `child_output_connections`, so one line stashing
`self._last_cal_meta = (response.get("calibration_status"), response.get("calibration_id"))` covers it,
seeded from the HELLO reply before the first poll. No new transport or thread.

Not from the PUB cache and not from a monitor poll — both checked, neither works:
`_post_to_internal_broker` drops non-numeric values before they reach the worker's `_pubsub_cache`
(`blacs_tabs.py:615-626`), so a status *string* can never ride it; and monitor connections are never
`CHECK_VALUE`-polled on this device (`check_all_remote_values` has no caller, and `status_monitor`
(`blacs_tabs.py:391`) is defined but never `statemachine_timeout_add`ed). The GUI also publishes
`calibration_id` on PUB (§(b)) — that copy feeds the **tab's** live display via the existing
`STATUS_TOPICS` extras path, not the h5 stamp.

Ceiling: the stamp can be one poll period (5 s) stale, so a recalibration inside that window mis-stamps
one shot. Acceptable — recalibration is operator-scale, and `calibration_id` changing at all is the signal.
The poll now runs in `MODE_POST_EXP` (parent `d66c782`), so there is no inter-shot blind window.

Raster shots keep the richer per-point stamp at `/data/{dev}/raster`
(`RasteringDevice/blacs_workers.py:320-323`). `"frame"` is **already** in both `raster_point_meta`
(`raster_controller.py:1456-1476`) and `RASTER_META_KEYS` (`RasteringDevice/blacs_workers.py:9`) as of
`5fede41`/`05a3acd` — do not re-add it. Only `calibration_id`, next to the existing
`calibration_matrix`/`calibration_offset`, remains.

## (e) Rollout across the three GUIs

| GUI | change |
|---|---|
| **Rastering** | `hello_extra` (`frames` + `calibration_id`), motor-frame rows in `_handle_program`, per-frame read routing + `_MONITOR_X`/`_MONITOR_Y` extension in `_handle_check`, new `_mm_monitor` + `calibration_id` PUB topics, `calibration_status`/`calibration_id` reply extras. |
| **HF_Locking** | None required. Frame-less scalars (THz setpoints). Optionally declare `frames: {"<port>": {"default": "absolute", "supported": ["absolute"], "units": {"absolute": "THz"}}}` — cosmetic. |
| **BigSky** | None required. Frame-less scalars (voltages, temperatures, delays). |
| **parent (BLACS)** | `zmq_v2.py` (`hello_extra`); `RemoteCommunication` (`frame` kwarg on `program_value` + `check_remote_value`, store `frames`/`calibration_id`); `RemoteControlWorker` (frame plumbing, `_last_cal_meta`, h5 attrs); `RemoteControlTab` (`child_frames`); `labscript_devices.py` (`frame` kwarg + property); `RasteringDevice` worker (`calibration_id` in the raster stamp); CT migration. |

No coordinated all-repo cutover: `frames` and `args["frame"]` are additive and optional in both directions,
so BLACS and the rastering GUI may restart in either order — unlike the v1→v2 hard sunset. The ordering
constraints are *semantic*, and both say **GUI build first**: (1) do not flip the CT to `frame="motor"`
before the GUI build routing motor-frame writes is running, or every raster write returns `invalid_frame`;
(2) do not repoint `Raster_{X,Y}_Monitor` to `laser_raster_{x,y}_mm_monitor` before the GUI publishes and
answers those topics, or the monitors go dark.

## (f) Failure modes

| Mode | Behavior |
|---|---|
| **Frame mismatch** (CT says `motor`, server's `supported` lacks it) | HELLO cross-check logs one ERROR naming connection + declared vs supported; connection still established (Q1: hint, not contract). The first write then fails typed `invalid_frame` — strict raise in `transition_to_buffered`, courtesy warn in `program_manual` via `_on_program_manual_error`. |
| **CT limits vs advertised `motor_limits`** | Mismatch logs one ERROR at HELLO (`(0, 25)` against `[0, 12]` would have caught the current mislabel). Never auto-corrected — the CT is the compile-time authority. |
| **Mid-session recalibration** | Motor-frame writes unaffected — the whole point. Pixel-frame values from before the re-fit now mean a different physical point; `calibration_id` change is the only detector, logged at WARNING on the first poll that sees it, and stamped per shot. Re-check `MOTOR_EDGE_CLAMP_MM` against the new cross-terms (open item (4)). |
| **GUI restart mid-queue** | **HELLO is NOT re-sent.** A transport failure calls `_reset_transport`, which only rebuilds the REQ socket and leaves `self.connected` True (`blacs_workers.py:193-204`); HELLO lives in `connect_to_remote` (`:220`), whose only callers are tab init and the operator's failed-button click (`blacs_tabs.py:238`, `:273`; Rastering `:293`, `:365`). That is exactly why `calibration_status`/`calibration_id` are **reply extras on the 5 s poll**, not HELLO-only: a GUI that came back uncalibrated or with a new fit is detected within one poll, so the h5 stamp cannot go silently stale. `declared_frames` *does* stay stale across a restart — benign, because per-request rejection is authoritative and `frames` only ever gated a log line. |
| **Uncalibrated pixel read** | Typed non-SUCCESS; `_skip_non_success_read` omits the channel from the snapshot (`check_remote_values`, `check_all_remote_values`). Never a motor number labelled px. |
| **Stale `frames`** (hot GUI config change, or the restart above) | Benign by construction: per-request rejection is authoritative and `frames` only ever gated a log line. |

Read-path caveat: `check_status` (`blacs_workers.py:615-630`) is the one read path using `_check_response`
(raises) rather than `_skip_non_success_read`, so a typed refusal there raises instead of skipping. Latent
only because `status_monitor` is never scheduled; a CT pixel monitor makes it reachable the day that timer
is armed. Convert it in the same pass, or leave `status_monitor` unscheduled deliberately and say so.

## (g) Test strategy (InMemoryTransport)

No sockets anywhere — `InMemoryTransport.pair()` (`zmq_v2.py:94-99`) drives every case.

- **`external_gui_lib/tests/`**: `hello_extra()` merged into the HELLO reply; default `{}` leaves it
  byte-identical; `encode_request` round-trips `args={"frame":...}`; `CANONICAL_CAPABILITIES` still pinned.
- **`GUIs/rastering/tests/test_zmq_v2_protocol.py`**: pixel write calibrated; motor write uncalibrated;
  single-axis in both frames; `invalid_frame` on a motor-only monitor; `CHECK_VALUE` echoes `frame`;
  `_mm_monitor` answers and PUB-ticks uncalibrated. Plus one `test_raster_pathmodel.py` case that a
  motor-frame move never clamps (it already covers `MOVE_TARGET` + clamp).
- **`RemoteControl/tests/`**: `program_value(frame="motor")` puts the key in `args`; `frame=None` is
  byte-identical to today; same for `check_remote_value`; `RemoteAnalogOut(frame="motor")` constructs
  and lands `frame` in `connection_table_properties`.
- **`RasteringDevice/tests/test_raster_stepping.py`** (FakeComms): CT `frame` reaches `args`; `"native"`
  omits it; all three attrs land on `/data/{dev}/monitor_values`; `invalid_frame` in `program_manual`
  routes through `_on_program_manual_error` (no sticky tab error).

Hardware acceptance (on top of §(c)'s compile + front-panel check): restart rastering GUI + BLACS together;
one shot programming both coords (expect one compound motor-frame message in the GUI log), one queue abort
with the GUI up (expect no red tab), then `/h5-inspect` for the new attrs.

## Open questions for the user

1. **Frame tokens** — keep `"motor"`/`"pixel"` as landed in `202004e`, or rename to `"motor"`/`"target"`
   to match the GUI's vocabulary (`target_to_motor`, `target_bounds`, `_last_target_xy`)? Cheap now; a
   coordinated flip after the migration.
2. **Default-frame stability** — the GUI's server-side default stays `"pixel"` even after the CT declares
   motor, since BLACS always sends the key. Keep that, or make `frame` mandatory on `laser_raster_xy`
   (typed `ERROR` when omitted) so a hand-driven debug client cannot inherit the wrong frame?
3. **Pixel monitors in the CT** — add `Raster_{X,Y}_Px_Monitor` on the existing `_coord_monitor` topics
   now (both frames in every shot h5, per the "show BOTH" decision), or keep the CT motor-only and read
   pixels from the raster stamp? Adding them is what makes the §(f) `check_status` caveat reachable.
4. **Sequence globals** — `RASTER_X = 2.12667` / `RASTER_Y = 1.07629` are already plausible mm and stay
   legal under `(0, 12)`, so nothing is forced. But were they *intended* as motor mm, or are they a stale
   uncalibrated target-space pair (target space equals mm only while uncalibrated)? If the latter, they
   need a real value first.
5. **`motor_limits` cross-check severity** — log an ERROR and continue (as drafted), or refuse to mark the
   device connected when the CT contradicts advertised travel?
6. **`calibration_status`/`calibration_id` on every reply** (5 s poll, two short strings) — fine, or
   restrict them to `CHECK_VALUE` replies to keep write replies minimal?
