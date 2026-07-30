# RemoteControl ZMQ Protocol v2

**Status**: IMPLEMENTED + CODE-REVIEWED (2026-05-23). All five PRs from
§9 shipped on topic branches across the 4 repos and pushed to RaXcollab
origins. Four parallel code-reviewer agents ran and findings were
addressed in a follow-up fixup commit per repo:

| Repo | Branch | Tip (post-fixup) |
|---|---|---|
| parent | `zmq-v2-cutover` | `928d9f6` (fixup) on `551a6c9` (cutover) on `cf394d3` (PR 1 patch) |
| `GUIs/BigSkyControl` | `zmq-v2-port` | `960b5b5` (fixup) on `9d30ac9` (port) |
| `GUIs/HF_Locking` | `zmq-v2-port` | `21079b7` (fixup) on `a0cd4b2` (port) |
| `GUIs/rastering` | `zmq-v2-port` | `2295bc8` (fixup) on `51d47d1` (port) — off `main`, in worktree `GUIs/rastering-zmq-v2/` |

Tests passing (105/105): 31/31 V1–V11 (labscript env) +
27/27 B1–B8 (BigSky, guis env) + 19/19 H1–H7 (HF, guis env;
+4 new H7 tests from review I3/I4/I5/C2) + 28/28 rastering
(13 existing + 15 v2, rastering env). v1 protocol is dead-code
on both client and server sides per Q4 §10-resolved hard sunset.

Review fixups summary:
  * Parent: `RemoteRetryableError` + `RemoteMalformedReplyError`
    exception subclasses (review I2/I3); `_check_response` surfaces
    `(retryable)` hint.
  * BigSky: `MAX_CONSECUTIVE_TRANSPORT_FAILURES=5` circuit breaker on
    `serve_once` exceptions (review I2).
  * HF_Locking: port range validation, `setpoint_not_initialized`
    UNKNOWN_CONNECTION on uninitialized CHECK_VALUE, explicit WARNING
    log when `wait_for_lock=True` but AND-gate conditions unmet
    (silent lock-bypass) — reviews C2/I3/I4/I5.
  * Rastering: `arm_raster` validate+commit consolidated into single
    lock critical section (review I-2); `serve_once` exception now
    `traceback.print_exc()` instead of `pass` (review I-3).

**Deployment**: branches stay on origin until the operator runs the
coordinated merge + restart sequence in
[`docs/zmq-v2-cutover-runbook.md`](zmq-v2-cutover-runbook.md).
After merge, BLACS + all 3 GUI processes must restart in any order;
no asymmetric-version window exists.

The v1 protocol reference doc at
[`docs/remotecontrol-zmq-protocol.md`](remotecontrol-zmq-protocol.md)
is preserved for archaeological context; new client/server code uses
v2 exclusively.

Origin of this spec: T0.5 audit (item 2.2,
[plan](../../.claude/plans/look-up-all-recent-purrfect-starfish.md)),
signed off 2026-05-22, shipped 2026-05-23.

---

## Context — why v2

The three RemoteControl external-GUI servers diverge significantly in their
implementation:

| GUI | Threading | Reply pattern | State ownership |
|---|---|---|---|
| HF_Locking | `ZMQRepWorker` + separate `ZMQPubWorker` (QThread × 2) | sync, `dict` reply | `SharedExperimentState` (mutex dict) |
| Rastering | inline daemon `_zmq_loop` on `raster_controller` | sync, `dict` reply | inline `SystemController` |
| BigSky | `BigSkyZmqServer` class + `concurrent.futures.Future` round-trip | async, structured `rejected:` envelope | `_lasers` dict of `SingleLaserController` |

**Convergence is needed at the *protocol* layer (message format + dispatch
contract), not at the *server* layer** (threading models legitimately differ
per-GUI). v1 was string-based + ad-hoc JSON; v2 standardizes the envelope
so:

- BigSky's first-class `rejected:` futures stop being a special case (BLACS-
  side worker `_check_response` no longer needs brittle string-prefix matching).
- New external-GUI devices can adopt a common `RemoteControlServerBase` with
  a `@handler("PROGRAM_VALUE")` decorator for dispatch.
- Tests (item 2.8) can mock the transport via a single `Transport` ABC.
- Protocol evolution is graceful: schema versioning + additive backwards
  compat through one migration period.

---

## 1. Message envelope

### 1.1 Negotiation (HELLO)

Client sends:

```json
{"v": 2, "action": "HELLO", "protocol_version": 2}
```

Server replies:

```json
{
  "v": 2,
  "status": "SUCCESS",
  "protocol_version": 2,
  "server": "LaserLockGUI",
  "capabilities": ["wait_for_lock", "monitors", "heartbeat"]
}
```

If the server reply omits `protocol_version`, the client falls back to v1
(legacy bare-string reply path). This is how v2 clients talk to v1 servers
during the migration window.

### 1.2 Request

```json
{
  "v": 2,
  "id": 17,
  "action": "PROGRAM_VALUE",
  "connection": "TiSa_set",
  "value": 348.666410,
  "args": {"wait_for_lock": true},
  "request_timestamp": 1747948800.123
}
```

- `v: 2` mandatory in every v2 request.
- `id: uint64` correlation id (echoed in reply). Currently REQ-REP is
  synchronous so `id` is redundant; reserved for future async/streaming
  features (e.g., long-running diagnostics).
- `args` named extension dict — v1's bare-key extras (`wait_for_lock`)
  move here for cleaner parsing.

> **Footnote — `wait_for_lock` AND-gate semantics (HF_Locking)**: when
> `args.wait_for_lock=True` reaches `LaserLockGUI`, the server only blocks
> on lock convergence if BOTH `lock_enabled` AND `deviation_mode` are True
> for that port. If either is False the server writes the setpoint and
> returns `SUCCESS` immediately, but emits a structured `WARNING` log
> (`outer.log_message.emit`) noting the silent lock-bypass. The
> `lock_enabled=True, deviation_mode=False` and inverse cases are
> covered by `tests/test_zmq_v2_protocol.py` H7 cases (added 2026-05-23
> per review C2). Callers that require enforcement must check the gate
> state via PUB-SUB cached monitors before issuing the request — there
> is no v2 status code for "wait requested but gate disarmed".
>
> As of 2026-07-07 the BLACS client always sends `wait_for_lock`
> explicitly (True or False) and the server treats an absent key as
> False — absence is never interpreted via server-side defaults.

### 1.3 Reply

```json
{
  "v": 2,
  "id": 17,
  "status": "SUCCESS" | "ERROR" | "REJECTED" | "TIMEOUT" | "UNKNOWN_CONNECTION",
  "value": 348.666410,
  "error": {
    "code": "rejected_did_not_take_effect",
    "message": "rejected: lpm0 did not take effect (got 1)",
    "retryable": false
  },
  "server_timestamp": 1747948800.456
}
```

- `status` enum (5 fixed tokens). Promotes BigSky's structured `rejected:`
  futures to first-class.
- `error` object only present when `status != SUCCESS`.
- `retryable` boolean — BLACS worker can decide whether to retry once vs.
  bubble error up to runmanager.

---

## 2. Dispatch contract

### 2.1 Explicit handler map (decorator-registered)

Server subclasses register handlers via class-level decorator:

```python
class LaserLockZmqServer(RemoteControlServerBase):

    @handler("PROGRAM_VALUE")
    def _handle_program(self, conn, value, args):
        ...

    @handler("CHECK_VALUE")
    def _handle_check(self, conn, args):
        ...
```

Base class owns the recv-loop, JSON parse, envelope construction, version-
check, and error wrapping. Subclasses only implement handler bodies.

**Rejected alternative**: name-convention dispatch
(`_handle_PROGRAM_VALUE`). Too magical; harder to grep; doesn't survive
rename refactors cleanly.

### 2.2 Reserved actions (v2 base implements)

| Action | Purpose | Notes |
|---|---|---|
| `HELLO` | Negotiate version + advertise capabilities | Base-class impl; subclass override allowed for capability list |
| `PING` | Liveness probe | Returns server uptime, monitor cadence; v2 base impl |
| `PROGRAM_VALUE` | Write a setpoint | Subclass implements |
| `CHECK_VALUE` | Read a setpoint/monitor | Subclass implements |

Subclass may register additional actions (e.g., HF_Locking's
`wait_for_lock` could become its own action instead of an `args` flag).

---

## 3. Liveness / heartbeat

### 3.1 PUB topic (unchanged from v1)

The `heartbeat` PUB topic continues at the existing per-server cadence:

| Server | Cadence |
|---|---|
| HF_Locking | 10 Hz (matches `_poll_fast`) |
| Rastering | ~1 Hz |
| BigSky | ~1 Hz (`HUB_LOOP_PERIOD_MS = 1000`) |

### 3.2 REQ-side PING action (new in v2)

Optional `PING` action on REQ socket returns server status:

```json
{"v": 2, "id": ..., "status": "SUCCESS",
 "uptime_seconds": 3724.5, "monitor_cadence_hz": 10,
 "subscriber_count": 1}
```

BLACS tab uses this to detect *stuck* PUB threads (PUB alive, REP dead) by
periodic ping with timeout < 1 s.

### 3.3 Tab-side stale-detect

If the tab observes no `heartbeat` for `3 × cadence_seconds`, mark
disconnected via the existing `_PubSubSignalBridge.pubsub_status_changed`
signal (already implemented for v1).

---

## 4. PUB-SUB topic format

### 4.1 Standardized form (mandatory)

```
"{connection}_{param}_monitor {value}"
```

Examples:

- `TiSa_set_setpoint_monitor 348.666410`
- `Raster_X_position_monitor 12.345`
- `YAG_1_temperature_monitor 30.5`

This unifies the current v1 divergence where HF_Locking uses bare port
numbers as topic prefixes. Existing topics will be re-emitted in the
standardized form during the migration window.

### 4.2 JSON payload (optional, opt-in via suffix)

For multi-field monitors (vector readbacks, structured status):

```
"{connection}_{param}_monitor:json {...JSON dict...}"
```

The `:json` suffix is the version-flag; v1 subscribers don't subscribe to
`:json` topics so they're invisible to legacy code. New subscribers can
opt in per topic.

---

## 5. Mockable transport

### 5.1 Transport ABC

```python
class Transport(Protocol):
    def send(self, frame: bytes) -> None: ...
    def recv(self, timeout_ms: int) -> bytes: ...
    def close(self) -> None: ...
```

### 5.2 Concrete implementations

| Class | Use |
|---|---|
| `ZmqReqTransport` | REQ socket; production client side |
| `ZmqRepTransport` | REP socket; production server side |
| `InMemoryTransport` | paired in-memory queue; tests inject this to bypass sockets |

`RemoteCommunication` (BLACS-side) and `RemoteControlServerBase` (GUI-side)
take a `Transport` in `__init__` (defaulting to ZMQ). Tests inject
`InMemoryTransport(server_side=...)` to drive request/response pairs without
binding any sockets — critical for item 2.8 (T0.4 invariant tests).

---

## 6. Observability

### 6.1 Structured log keys

Every request/response logs:

```
{
  "ts": 1747948800.123,
  "server": "LaserLockGUI",
  "action": "PROGRAM_VALUE",
  "conn": "TiSa_set",
  "id": 17,
  "status": "SUCCESS",
  "latency_ms": 12.3,
  "error_code": null
}
```

### 6.2 Logger namespace

`remotecontrol.{server_name}.{req|pub}`. Example:

- `remotecontrol.LaserLockGUI.req` — REQ-REP server activity
- `remotecontrol.LaserLockGUI.pub` — PUB-SUB broadcast activity

Replaces ad-hoc `self._log("ZMQ: PROGRAM_VALUE ...")` calls in BigSky and
`self.log_message.emit(...)` in HF_Locking.

---

## 7. Backwards compatibility

### 7.1 Purely additive

v2 servers MUST accept v1 requests (missing `v` key → respond in v1
string/dict form per the existing protocol). v2 clients downgrade on
HELLO if server omits `protocol_version` in reply.

### 7.2 BLACS-side client behavior

`userlib/user_devices/RemoteControl/RemoteCommunication.py` sends `v: 2`
once **all three** GUIs ship v2; until then it sends v1 (current shape)
and parses both reply forms. Cleanup of the v1 dual-path code is a
separate post-v2 ticket.

### 7.3 Sunset policy

v1 sunset is **deferred to a follow-up** — out of scope for item 2.2.
After all three GUIs ship v2, a future PR can change the policy from
"accept v1" to "warn on v1" and eventually "refuse v1". Lab tooling
outside this repo (external scripts using HELLO?) needs a survey first.

---

## 8. Migration order

1. **BigSky first** — already structured-reply (`rejected:` futures via
   `_handleRemoteCommand` / `executeRemoteCommand`, commit `6c72b49`); the
   cleanest template for `RemoteControlServerBase`. Lowest blast radius
   (single hub, single GUI restart per laser).

2. **HF_Locking second** — has `SharedExperimentState` + QThread workers;
   clean separation makes base-class adoption straightforward. The 10 Hz
   wavemeter cadence will stress the base loop and validate perf.

3. **Rastering last** — `_zmq_loop` is inline at `raster_controller.py:1585`,
   tightly coupled to controller state. Refactor risk highest; do last
   with both other migrations as templates. Coordinated with rastering
   camera Spinnaker migration (separate session).

---

## 9. Implementation outline (NOT yet executed)

Estimated PR breakdown — one per repo to minimize blast radius:

1. **parent repo** — add `userlib/external_gui_lib/{__init__.py,zmq_v2.py}`
   defining `RemoteControlServerBase`, `Transport` ABC, concrete `ZmqReqTransport` /
   `ZmqRepTransport` / `InMemoryTransport`, `@handler` decorator, the v2
   envelope helpers. Plus client-side `RemoteCommunication` v2 dual-path
   parser in `userlib/user_devices/RemoteControl/RemoteCommunication.py`.

2. **GUIs/BigSkyControl** — port `BigSkyZmqServer` to inherit from
   `RemoteControlServerBase`. Dispatch via decorated handlers. PUB topic
   re-emit in standardized form (keep legacy emit for migration window).

3. **GUIs/HF_Locking** — port `ZMQRepWorker` to inherit. `ZMQPubWorker`
   stays separate (still a QThread for cadence isolation).

4. **GUIs/rastering** — port `_zmq_loop` to inherit. Daemon-thread model
   preserved.

Each PR independently mergeable and reversible. v1 path stays alive at
every step.

---

## 10. Open questions for user (RESOLVED 2026-05-22)

Original draft listed four open questions. All four are resolved below
(§10-resolved). The original Q1–Q4 framing is preserved for historical
context.

### Original questions (historical)

1. **Hub-mode capability advertisement** — BigSky is a hub of N lasers,
   each with its own connection prefix (`YAG_1_*`, `YAG_2_*`). Should
   `capabilities` enumerate connection prefixes (e.g.,
   `connections: ["YAG_1_*", "YAG_2_*"]`) so BLACS can fail-fast on typos
   at HELLO time rather than at first CHECK_VALUE? Or leave per-call?
2. **`id` correlation** — REQ-REP is synchronous so `id` is currently
   redundant. Do we want it for future async/streaming (e.g., long-running
   `wait_for_lock` could become a stream of progress events), or YAGNI?
3. **Capabilities or feature flags** — `["wait_for_lock", "heartbeat"]`
   enum vs. monotonic `feature_level: int`. Enum is more flexible but
   harder to test exhaustively.
4. **v1 sunset date** — soft (warn on v1 receive) or hard (refuse) after
   all three migrate? External-script survey needed first.

### §10-resolved (canonical — supersedes the open questions above)

#### Q1 — Hub-mode capability advertisement: OPTIONAL prefix-match glob

- HELLO reply MAY include a top-level `"connections"` key with an array of
  string patterns. Hub-mode servers (BigSky) SHOULD advertise; single-
  instance servers (HF_Locking, Rastering) SHOULD omit.
- **Pattern format**: a string ending in `*` matches by **prefix only**.
  No other glob/regex metacharacters supported.
- **BLACS-side check** (canonical algorithm):

  ```python
  any(conn.startswith(p.rstrip("*")) for p in advertised_connections)
  ```

- **NO** `fnmatch`, **NO** recursive `**`, **NO** character classes `[abc]`.
  Three lines of matcher code, zero library dependency.
- Advertisement is a **hint, not a contract**. BLACS-side MUST still
  gracefully handle `UNKNOWN_CONNECTION` for any request; a server MAY
  advertise stale data during a hot config change.

#### Q2 — `id` correlation: REQUIRED from BLACS, OPTIONAL from others

- v2 requests MAY include `"id": uint64` (monotonically increasing per
  (client, server) pair).
- **BLACS-side `RemoteCommunication` MUST emit `id` on every outbound
  request.** Other clients (debug scripts, future external tools) MAY
  omit. Servers MUST echo `id` if present; MUST NOT reject requests that
  omit it.
- **Rationale**: half-instrumented logs are useless for correlation.
  Forcing `RemoteCommunication.send_request` to always emit `id` keeps the
  `remotecontrol.{server}.req` structured log (§6) reliably joinable
  end-to-end at one uint64 per message.
- **Implementation**: `RemoteCommunication` ships a per-instance counter
  (`self._id_counter = itertools.count()`); `id = next(self._id_counter)`
  on every send. Resets on reconnect (acceptable — the broken connection
  itself is the correlation breakpoint).
- Not a streaming commitment. If future async/streaming lands, `id` is
  already the correlation handle.

#### Q3 — Capabilities: enum strings + CANONICAL_CAPABILITIES frozenset

- `capabilities` is an **array of strings** drawn from a fixed canonical set.
- **Canonical set** (module-level constant in
  `userlib/external_gui_lib/zmq_v2.py`):

  ```python
  CANONICAL_CAPABILITIES = frozenset({"monitors", "heartbeat", "wait_for_lock"})
  ```

- **Invariant test** (item 2.8 pattern): every capability string emitted by
  a v2 server MUST be in `CANONICAL_CAPABILITIES`. New capabilities
  require a two-step PR: (1) extend `CANONICAL_CAPABILITIES`, (2) use it.
- **NO** `feature_level: int`. Lab features are orthogonal: HF_Locking has
  `wait_for_lock` (`workers.py:595`), BigSky has `monitors` (PUB-SUB temp/
  voltage cache), Rastering has `monitors` only. Coupling them via an int
  forces a server that adds a new feature to claim all earlier ones it
  doesn't implement.
- Precedent: ZMQ itself uses string-mechanism advertisements (`NULL`,
  `CURVE`, `PLAIN`); HTTP uses Accept enum headers.

#### Q4 — v1 sunset: HARD SUNSET at v2 release (no dual-path code)

- **External-HELLO survey ran 2026-05-22**:
  - Searched `C:\Users\radmo\MIT Dropbox\Shungo Fukaya\Experiments\Main_Experiment\`
    for `import zmq` / `zmq.` / `tcp://` / `action.*HELLO` patterns.
  - **Result**: zero matches. Only `.ipynb` analysis notebooks exist in
    the operator tree (no `.py` scripts). Initial keyword hits were
    incidental matches inside PNG base64 blobs.
  - No external code calls HELLO/REQ on ports 3796, 55535, 55540.
- **v2 server behavior on v1 request**: return
  `{"status": "ERROR", "error": {"code": "v1_protocol_refused",
  "message": "Server requires v2 protocol; client must include 'v': 2 in
  requests"}}`. No fallback path. No dual-path code.
- **BLACS-side `RemoteCommunication`**: ships v2-only from day 1. The
  dual-path parser that §7.2 originally described is **not written**.
- **Migration order**: BLACS + all three GUIs (BigSky, HF, Rastering)
  ship v2 in one coordinated round. Since they're co-located on this PC
  under one operator, no asymmetric-version window exists.
- **Net**: ~50–80 lines of dual-path code that would have lived in
  `RemoteCommunication.py` are never written. **Section 7.1 (purely
  additive)** is superseded by this v2-only stance.

### Resolution sign-off

All four resolutions signed off by user 2026-05-22. The spec is
implementation-ready. Next concrete step: begin §9 PR rollout.

---

## 11. References

- v1 protocol: [`docs/remotecontrol-zmq-protocol.md`](remotecontrol-zmq-protocol.md)
- External GUIs overview: [`docs/external-guis-architecture.md`](external-guis-architecture.md)
- BigSky futures plumbing landed in commits `6c72b49`, `dc6c736`, `d37b822`,
  `eafc229`, `1eb2321` (BigSkyControl sub-repo).
- Audit memory: `~/.claude/projects/c--Users-radmo-labscript-suite/memory/reference_two-remotecontrol-trees.md`
- Plan: `~/.claude/plans/look-up-all-recent-purrfect-starfish.md` (T0.5, item 2.2)

---

## 12. Client-side typed-status contract (BLACS worker)

The base `RemoteControlWorker` is the behavioral contract every device inherits
(LaserLock has no `blacs_workers.py` — it is pure base). Policy for typed replies:

- **Read/poll/snapshot** (`check_remote_values`, `check_all_remote_values`): a
  non-SUCCESS reply → `_skip_non_success_read` logs a warning and skips that
  channel. A read NEVER raises (a raising periodic poll bricks the tab with a
  persistent error banner — the 2026-07-14 Blocker-A signature).
- **Write** (`program_manual`, buffered `program_value`): `_check_response` raises
  on any non-SUCCESS — real failures surface / abort the shot.
- Device-specific divergence (e.g. BigSky buffered skip-unlaunched via
  `should_skip_buffered_response`) is an explicit, tested override — not the norm.
- **Behavior note:** an un-programmed channel (HF `CHECK_VALUE` →
  `UNKNOWN_CONNECTION`) is now **omitted** from the monitor snapshot, where v1's
  always-SUCCESS `CHECK_VALUE` recorded a bogus `0.0`. Normally-programmed channels
  are unchanged; analysis reads per-channel keys, so a missing unset channel is safe.

When adding a device (`/new-device`), use the base worker; do NOT re-implement
dispatch or copy BigSky's overrides. Rationale + generalization:
`memory/feedback_remotecontrol-base-is-the-contract.md`.
(Post-merge follow-up: add a pointer to this section from `docs/device-internals.md`,
which lives on `master`.)
