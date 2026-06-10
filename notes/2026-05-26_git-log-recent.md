# Git Log — Recent Activity (as of 2026-05-26)

Multi-repo snapshot across the labscript-suite workspace.

---

## Since last Thursday (2026-05-21 → 2026-05-26)

### Parent repo (`labscript-suite`) — 29 commits

**On master (HEAD = `069c2ca`):**

| SHA | Subject |
|---|---|
| `069c2ca` | docs(CLAUDE): add session handoff path + REPL conda-activate gotcha |
| `ae493e9` | docs(matisse): rewrite with concrete remote-control protocol findings (LocalGoTo, Network DLL, no Counterdrift API) |
| `1b0693a` | Merge branch refactor/zmq-v2-hardening into master |
| `0bb8722` | fix(zmq-v2): harden handler contract + drop JSON re-decode hot path |
| `93d2488` | docs(matisse): rewrite external-lock reference + add parallel-investigation runbook |
| `a07bf03` | Merge branch refactor/zmq-v2-base into master |
| `ef24a6d` | feat(zmq-v2): add userlib/external_gui_lib/ protocol foundation (item 2.2 PR 1/4) |
| `6795f4a` | Merge branch refactor/zmq-protocol-v2-spec into master |
| `9d1abc9` | Merge branch 'refactor/raster-checkbox-persistence' into master |
| `242dc99` | Merge branch 'refactor/subscriber-registry' into master |
| `e2b9f68` | Merge branch 'refactor/remotecontrol-graveyard-cleanup' into master |
| `a30346d` | Merge branch 'refactor/fix-jim-dio-enh-refs' into master |
| `ec03e3a` | docs(zmq-v2): fold §10-resolved Q1-Q4 sign-off into spec |
| `3f3239a` | fix(sequences): jim_DIO_acquire ENH_start/ENH_end → ENH_START/ENH_DURATION (T0.8, item 2.9) |
| `65addcf` | docs: add ZMQ v2 protocol spec (item 2.2 design, not yet implemented) |
| `538dbd3` | refactor(RasteringTab): persist raster_check_box state across BLACS restarts |
| `11db110` | refactor(RemoteControl): data-driven subscriber registry (replaces RasteringTab wholesale override) |
| `4d46acb` | refactor: rename graveyard CTs to .py.bak (companion to dead-tree deletion) |
| `aca9b13` | docs: add Matisse C external-lock reference (DSP-input vs External PID) |

**Off-master branches:**

| SHA | Branch | Subject |
|---|---|---|
| `e2147ab` | `tests/userlib-worker-tests` | fix(NI_SCOPE): R3 review fixups — log behavior + missing parametrize cases |
| `10c5eca` | `chore/subagent-rule-inheritance` | chore(agent-workflow): R1 review fixups — reorder + hoist reviewer-prompt rule |
| `0884b49` | (no branch) | feat(2.8c): SDK-free worker helpers + tests + pre-push hook (Track 1) |
| `40d9a27` | `docs/zmq-v2-spec-footnote` | docs(zmq-v2): add wait_for_lock AND-gate footnote (HF M6, item 2D) |
| `c8d21dc` | (no branch) | chore(agent-workflow): document subagent context inheritance + canonical-doc injection rule |
| `645fa0d` | `feat/spinnaker-gige` | docs: rastering uEye → Spinnaker migration update |
| `1cbbbcf` | `zmq-v2-cutover` | docs(matisse): rewrite with concrete remote-control protocol findings |
| `5863d35` | `origin/zmq-v2-cutover` | docs(zmq-v2): BLACS_COMMUNICATION_CONTRACT deprecation banner |
| `2e751c5` | (no branch) | docs(zmq-v2): sync parent CLAUDE.md + reference docs to v2 canonical |
| `928d9f6` | (no branch) | fix(zmq-v2): apply review findings to parent (post-cutover review) |
| `551a6c9` | (no branch) | refactor(zmq): cut over RemoteCommunication to v2-only (item 2.2 PR 4b) |
| `cf394d3` | (no branch) | fix(zmq-v2): translate zmq.Again → TimeoutError in REQ/REP transports |

### `labscript-devices` — 2 commits

| SHA | Subject |
|---|---|
| `e975eeb` | Merge branch 'chore/remove-dead-remotecontrol' into master |
| `f5225ef` | chore(RemoteControl): remove dead tree; userlib copy is canonical |

### `blacs`, `labscript-utils` — no commits

**Themes of the week:** ZMQ v2 protocol cutover (design → impl → hardening → merge → docs), Matisse external-lock investigation/rewrite, RemoteControl graveyard cleanup, rastering checkbox persistence, subagent context-inheritance docs.

---

## The 2 weeks before that (2026-05-07 → 2026-05-20)

### Parent repo — 11 commits

| SHA | Subject |
|---|---|
| `f08647b` | data: snapshot BaF_globals.h5 baseline (operator edits) |
| `47fe9c2` | docs(notes): wrap-up lab notes from 2026-05-15 + 2026-05-19 sessions |
| `2ef4cb9` | fix: NuvuCamera ctypes mis-assigns + NI_SCOPE stale log strings (Tier 5.1 + 5.4) |
| `decf7c9` | docs: canonical refs for state machine / ZMQ protocol / experiment / GUIs / latent issues (Tier 3) |
| `5431926` | docs: fix audit-flagged drift across docs / agents / rules / CLAUDE.md (Tier 1+2+4) |
| `b9453f2` | docs: point backend repos at RaXcollab forks (was shafinulh) |
| `c9822f3` | refactor(agents): rename labscript-amo-expert → amo-expert; multi-agent orchestration + doc sync |
| `d974676` | chore: checkpoint accumulated multi-session work |
| `8a79704` | chore(memory): back up auto-memory; record python3-shim plugin-hook fix |
| `dd7fab6` | docs(hf-locking): use-gated render spec + BLACS stale-broadcast fix; deferred follow-ups |
| `b328f9f` | Rastering: snapshot from live drain cache; remove redundant post_experiment override |

### `labscript-devices` — 1 commit

| SHA | Subject |
|---|---|
| `aed191f` | fix: replace Py3.8+ removed APIs in latent-unused drivers (upgrade insurance) |

### `labscript-utils` — 1 commit

| SHA | Subject |
|---|---|
| `25cee8c` | fix(device_registry): replace `import imp` with `importlib.util` (Py 3.12 compat) |

### `blacs` — no commits

**Themes:** documentation audit & canonical refs build-out (Tier 1-5), agent renaming/orchestration cleanup, NuvuCamera + NI_SCOPE fixes, Py 3.12 compat patches in backend, HF_Locking render spec doc.

---

*Generated 2026-05-26.*
