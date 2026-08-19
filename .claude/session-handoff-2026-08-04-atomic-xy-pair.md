# Handoff: Atomic (x,y) write for RasteringDevice — ready-to-implement spec

**Status: design verified by blacs-expert 2026-08-04 (file:line evidence). NOT implemented. Verdict: contained worker + GUI-server change, ~30-40 LOC across 2 files — NOT a connection-table/tab refactor.**

## Why

Today "set the position" is two independent single-axis ZMQ writes (x then y). Three problems, all deleted by one compound write:
1. **Physical intermediate excursion**: the motors visit `(x_new, y_old)` between the writes; if that composite maps outside travel the x-write is refused even when both endpoints are legal. The 10 µm edge clamp CANNOT fix this one.
2. **Torn echo pairs** (read side benefits indirectly): the true destination is asserted as one pair.
3. x-before-y ordering rests on alphabetical `Raster_X` < `Raster_Y` labscript-name sort — atomicity makes ordering moot (motor identity is already serial-pinned in `GUIs/rastering/config.py`; SN solves identity, not order).

## Design (worker-level interception — no new BLACS channel)

The tab, widgets, connection table, PUB topics, and read-side poll ALL stay unchanged. Intercept where both values already co-exist:

### GUI side (`GUIs/rastering/raster_controller.py`) — ~10-15 LOC
- Add a compound name (e.g. `laser_raster_xy`) accepted by `_RasteringV2Server._handle_program` alongside `_WRITABLE_COORDS` (`:349`): value = 2-sequence `[x, y]`, pixel/target units by default. **Anticipate the frame-explicit direction** (user-decided 2026-08-04, see `session-handoff-2026-08-04-raster-echo-chain.md` Units direction): accept an optional `frame` in the v2 `args` dict (`"pixel"` default, `"motor"` bypasses the calibration and maps to the existing MOVE_MOTOR path) so motor-frame communication can land later without a second protocol change.
- Execute via **existing** `request_move_target` (`:780-792`) → `MOVE_TARGET` path — already does one `target_to_motor` on the true pair, one `clamp_to_bounds`, one bounds check, then both axes (`:1965-1994`). No new controller logic.

### BLACS side (`userlib/user_devices/RasteringDevice/blacs_workers.py`) — ~15-20 LOC
- `program_manual` override: pull both coords from `front_panel_values` (it receives the whole panel), send ONE compound `program_value`, skip the per-channel sends for the two coord connections.
- `transition_to_buffered`: the `remote_device_operation` row has both columns → compound send when both present.

## Gotchas (both verified — do not skip)

1. **One-column table**: `generate_code` emits a column only for channels where `value_set()` is true (`RemoteControl/labscript_devices.py:280-291`). A sequence setting only `Raster_X` → keep the EXISTING single-axis path for that case. **NEVER fill the missing axis from `front_panel_values`** — that's the 5 s-stale echo, i.e. reintroducing the incident. The GUI already pairs single-axis moves with a fresh encoder read (`raster_controller.py:1928-1943`, landed `9608d72`) — that is the correct partner.
2. **Courtesy-write policy**: a compound failure in `program_manual` must route through `_on_program_manual_error` (once, with a synthetic connection label like `laser_raster_xy`) — an inlined try/except silently kills the courtesy policy and a refused pair becomes a sticky tab error again (blocks all later shots until dismissed). Strict raise stays in `transition_to_buffered`.

## Non-issues (verified)

- Compound name is never a labscript child → never polled → no `unknown_connection` storm; tab drops unknown keys via `connection in self._AO`.
- `_check_response` is connection-agnostic — no change (do put both values in the context string).
- Read side: leave alone, zero LOC — `CHECK_VALUE` is a lock-protected read of the cached tuple; two polls read the same snapshot. (Torn pairs across the two READ round-trips remain theoretically possible but harmless once writes are atomic.)
- No ADVERTISED_CONNECTIONS gating anywhere (`external_gui_lib/zmq_v2.py:253,322,361-362` — definition only, no callers).

## Tests

- GUI: `GUIs/rastering/tests/test_zmq_v2_protocol.py` (InMemoryTransport pattern) — compound PROGRAM_VALUE happy path, bad-shape value, uncalibrated behavior; `tests/test_raster_pathmodel.py` already covers MOVE_TARGET/clamp.
- BLACS: `userlib/user_devices/RasteringDevice/tests/test_raster_stepping.py` (FakeComms pattern) — compound send on full panel, single-axis fallback on one-column table, failure routes through `_on_program_manual_error`.

## Verify after landing

Compile CT (no changes expected), restart rastering GUI + BLACS together, run: (a) a shot programming both coords, (b) a shot programming only x, (c) a queue abort with the GUI on — confirm one compound message in the GUI log for (a), single-axis for (b), no red tab for (c). Check h5 `remote_device_operation` unchanged.
