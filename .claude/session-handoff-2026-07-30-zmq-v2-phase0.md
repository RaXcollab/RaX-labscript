# Session handoff — zmq v2 cutover, Phase 0 (2026-07-30)

Continue the zmq v2 cutover. All 4 review blockers are resolved locally and
**NOTHING is pushed yet** — full state is in auto-memory (`zmq-v2-cutover-dependency`)
and the committed review doc (`docs/zmq-v2-cutover-review-2026-07-30.md`, master
@ `a19d8f7`). The authoritative procedure is `docs/zmq-v2-cutover-runbook.md` **on the
cutover branch**: `.claude/worktrees/zmq-v2-cutover` (branch `zmq-v2-cutover` @ `454d601`).

## Do now — runbook Phase 0 remainder, one repo at a time (subagents ok)

Merge each GUI's own `main` INTO its port branch (`main` is not an ancestor of any
of the three), then re-run that GUI's tests with `ZMQ_V2_REQUIRED=1` and
`PYTHONPATH='C:\Users\radmo\labscript-suite\.claude\worktrees\zmq-v2-cutover\userlib\external_gui_lib'`:

| Repo | Branch @ tip | Env | Expected |
|---|---|---|---|
| `GUIs/rastering-zmq-v2` | `zmq-v2-port` @ `c670dfd` | `rastering` | 18 protocol / 69 total |
| `GUIs/HF_Locking-zmq-v2` | `zmq-v2-port` @ `aa99a75` | `guis`, deselect H6 | 19 passed |
| `GUIs/BigSkyControl` | `zmq-v2-port-rebuilt` @ `c38e6ab` | `guis` | 38 passed |

BigSky's checkout is parked on `main` on purpose (lab safety) — do the merge via the
branch, put `main` back after.

## Then STOP and ask before runbook Phase 1 (the push round)

HF `main` (6), rastering `main` (2), BigSky `main` (1), parent `master` (~29 —
recount), the three port branches, parent cutover branch.

## Traps (also in the runbook)

- Never merge BigSky's old `zmq-v2-port` (`df8be86`) or its `refactor/*` branches —
  poisoned base; their payload is already in `zmq-v2-port-rebuilt`.
- Never `git rebase origin/zmq-v2-port` in rastering.
- HF port push needs `--force-with-lease` (divergence verified benign, range-diff
  patch-identical).
- HF: merge port INTO `main`; never copy branch files over main, never squash.
- Never stage `calibration_data.json`.
- Every python via `source ~/miniconda/etc/profile.d/conda.sh && conda activate <env>`.
