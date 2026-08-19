# Claude-mem Tuning — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans`. This is a **configuration tuning + verification** plan, not a code-TDD plan. Replace "write failing test → implement → pass" with **"snapshot → apply → verify with curl"**. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish initializing claude-mem (enable MCP + folder CLAUDE.md, resolve broken chroma) and tune injection + capture so per-prompt cost drops from ~21k → ~3-5k tokens without losing any user-valued skill (`learn-codebase`, `smart-explore`, `babysit`).

**Architecture:** Three workstreams, applied in order against the running worker daemon at `http://127.0.0.1:37777`:
1. **Track A — Init**: enable MCP (REST POST), resolve chroma (settings.json + restart), enable folder-local CLAUDE.md injection.
2. **Track B — Tune**: edit `~/.claude-mem/settings.json` once with the combined injection-trim + capture-trim block.
3. **Documentation + follow-ups**: add CLI safety rule, stub three Track C follow-up plans.

**Tech Stack:** PowerShell + curl REST calls to worker, JSON edits to `~/.claude-mem/settings.json`, native-memory text edits, Markdown stub files. Conda activation NOT required for any step (claude-mem runtime is independent of the labscript conda env).

**Source spec:** [`.claude/docs/superpowers/specs/2026-05-24-claude-mem-tuning-design.md`](../specs/2026-05-24-claude-mem-tuning-design.md)

---

## File Structure

**Files modified (NOT in git):**
- `~/.claude-mem/settings.json` — the canonical tuning surface
- `C:\Users\radmo\.claude\projects\c--Users-radmo-labscript-suite\memory\MEMORY.md` — append CLI-safety pointer line

**Files modified (in labscript-suite git):**
- `c:\Users\radmo\labscript-suite\CLAUDE.md` — one bullet added to "Do NOT Flag These" section

**Files created (not in git):**
- `C:\Users\radmo\.claude\plans\backups\claude-mem-settings-2026-05-24.json` — settings.json snapshot
- `C:\Users\radmo\.claude\plans\backups\claude-mem-runtime-2026-05-24.json` — `/api/settings` snapshot
- `C:\Users\radmo\.claude\plans\backups\claude-mem-injection-size-baseline-2026-05-24.txt` — pre-change injection size

**Files created (in labscript-suite, NOT yet committed — stub follow-up plans):**
- `c:\Users\radmo\labscript-suite\.claude\docs\superpowers\plans\2026-05-24-pathfinder-architectural-audit.md` (Track C1 stub)
- `c:\Users\radmo\labscript-suite\.claude\docs\superpowers\plans\2026-05-24-knowledge-agent-corpora.md` (Track C2 stub)
- `c:\Users\radmo\labscript-suite\.claude\docs\superpowers\plans\2026-05-24-make-plan-vendor-hardware-adoption.md` (Track C3 stub)

**Files untouched:**
- `~/.claude-mem/claude-mem.db` — DB and observations are never modified by this plan
- All `~/.claude/plugins/cache/thedotmack/claude-mem/13.*/` — plugin bundles untouched
- Any labscript code under `userlib/`, `blacs/`, `labscript-devices/`, `labscript-utils/`, `GUIs/`

---

## CLI Safety Reminders (load-bearing — read before every shell call)

These are derived from `~/.claude/projects/c--Users-radmo-labscript-suite/memory/reference_claude-mem-cli-surface.md`:

- **`npx claude-mem` with no args → runs install**. `npx claude-mem <anything-with-leading-dash-not-in-whitelist>` → runs install. Only `-h/--help/-v/--version` are whitelisted.
- **`npx claude-mem install --help` ALSO runs the installer**. There is no `--help` parsing inside the install handler.
- **Safe read-only commands**: `npx claude-mem version`, `npx claude-mem search <query>`, `npx claude-mem help`, `npx claude-mem status` (unreliable PID-file probe — prefer REST API).
- **Safe restart**: `npx claude-mem restart` IS in the spec and IS allowed for this plan. It is "NO in agent context without authorization", which this plan provides — but flag it visibly in every step that uses it.
- **NEVER run in this plan**: `install`, `repair`, `update`, `upgrade`, `uninstall`, `remove`, `adopt` (without `--dry-run`), `cleanup` (without `--dry-run`), `transcript watch`, any `server start/stop/restart/api-key/jobs retry/jobs cancel` variant.
- **For diagnostics, prefer REST API** at `http://127.0.0.1:37777/api/admin/doctor` over `npx claude-mem status`.

---

## Task 0: Pre-flight — confirm worker is healthy

**Files:** (none)

- [ ] **Step 1: Confirm worker is listening on port 37777**

Run (PowerShell):
```powershell
netstat -ano | Select-String "37777"
```
Expected: at least one row containing `LISTENING` and `127.0.0.1:37777`.

If nothing LISTENING → STOP. Worker is down. Investigate before continuing (do NOT auto-start via `npx claude-mem start` from this plan — flag to user first).

- [ ] **Step 2: Confirm worker `/api/health` returns 200**

Run (bash or PowerShell — `curl.exe` is on PATH):
```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:37777/api/health
```
Expected output: `200`.

If non-200 → STOP. Worker process exists but is not serving. Flag to user.

- [ ] **Step 3: Confirm plugin version**

Run:
```bash
curl -sS http://127.0.0.1:37777/api/health | grep -oE '"version":"[^"]+"'
```
Expected: `"version":"13.3.0"` (per spec, v13.3.0 is the active resolved version after the accidental install).

If output is `13.2.0`, the older bundle is somehow active again — proceed but note this for the wrap-up.

- [ ] **Step 4: Create backup directory**

Run:
```bash
mkdir -p /c/Users/radmo/.claude/plans/backups
```
Expected: directory exists, no error.

---

## Task 1: Snapshot current state (rollback insurance)

**Files:**
- Create: `C:\Users\radmo\.claude\plans\backups\claude-mem-settings-2026-05-24.json`
- Create: `C:\Users\radmo\.claude\plans\backups\claude-mem-runtime-2026-05-24.json`
- Create: `C:\Users\radmo\.claude\plans\backups\claude-mem-injection-size-baseline-2026-05-24.txt`

- [ ] **Step 1: Copy current `settings.json` to backup**

Run:
```bash
cp ~/.claude-mem/settings.json /c/Users/radmo/.claude/plans/backups/claude-mem-settings-2026-05-24.json
```
Expected: file exists with the same byte size as the source.

Verify:
```bash
diff ~/.claude-mem/settings.json /c/Users/radmo/.claude/plans/backups/claude-mem-settings-2026-05-24.json
```
Expected: no output (identical).

If `~/.claude-mem/settings.json` does not exist, **create it with `{}`** first — claude-mem defaults still apply but the file becomes the override surface:
```bash
test -f ~/.claude-mem/settings.json || echo "{}" > ~/.claude-mem/settings.json
```

- [ ] **Step 2: Snapshot the live runtime config**

Run:
```bash
curl -sS http://127.0.0.1:37777/api/settings > /c/Users/radmo/.claude/plans/backups/claude-mem-runtime-2026-05-24.json
```
Expected: file exists; contains `"CLAUDE_MEM_MODEL"`, `"CLAUDE_MEM_MODE"`, etc.

Verify it has 70+ keys (per spec: "70 = `CLAUDE_MEM_*`"):
```bash
grep -c "CLAUDE_MEM_" /c/Users/radmo/.claude/plans/backups/claude-mem-runtime-2026-05-24.json
```
Expected output: an integer ≥ 65 (allowing for line-wrap variation).

- [ ] **Step 3: Record baseline per-prompt injection size**

Run:
```bash
curl -sS "http://127.0.0.1:37777/api/context/inject?project=labscript-suite" | wc -c > /c/Users/radmo/.claude/plans/backups/claude-mem-injection-size-baseline-2026-05-24.txt
cat /c/Users/radmo/.claude/plans/backups/claude-mem-injection-size-baseline-2026-05-24.txt
```
Expected: a number, roughly 18000–25000 bytes (the ~21k from the spec). Record this — Task 7 will compare against it.

If the endpoint returns 404 or 500, this endpoint may differ between versions. Try the alternate:
```bash
curl -sS "http://127.0.0.1:37777/api/context/recent?project=labscript-suite" | wc -c
```
Use whichever returns a sensible byte count; note which one in the baseline file.

---

## Task 2: Track A1 — Enable MCP server

**Files:** (none — REST state only)

- [ ] **Step 1: Verify MCP is currently disabled**

Run:
```bash
curl -sS http://127.0.0.1:37777/api/mcp/status
```
Expected: JSON containing `"enabled":false`. (If already `true`, MCP was re-enabled elsewhere — record this and skip Steps 2-3.)

- [ ] **Step 2: Enable MCP via REST POST**

Run:
```bash
curl -sS -X POST http://127.0.0.1:37777/api/mcp/toggle \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```
Expected: JSON response containing `"enabled":true` (or `"ok":true`).

- [ ] **Step 3: Confirm MCP is now enabled**

Run:
```bash
curl -sS http://127.0.0.1:37777/api/mcp/status
```
Expected: JSON containing `"enabled":true`.

- [ ] **Step 4: Confirm MCP tools are reachable from this session**

In this Claude Code session, attempt to call:
```
mcp__claude_mem__smart_search(query="post_experiment", path=".")
```
Expected: either ToolSearch reports `mcp__claude_mem__smart_search` discoverable, OR an error indicating Claude Code needs a restart to register newly enabled MCP tools.

If a restart is required to register the tools, this is expected — note it; Task 6 already plans a full Claude Code restart. **Do not restart Claude Code in this task.**

---

## Task 3: Track A2 — Test chroma persistent mode

**Files:**
- Modify: `~/.claude-mem/settings.json` (add ONE key `CLAUDE_MEM_CHROMA_MODE`)

This task is **decision-branching**. If persistent mode is healthy → proceed to Task 5. If not → Task 4 disables chroma entirely, then Task 5.

- [ ] **Step 1: Read current settings.json**

Run:
```bash
cat ~/.claude-mem/settings.json
```
Capture the output. We will edit it to add the `CLAUDE_MEM_CHROMA_MODE` key.

- [ ] **Step 2: Edit settings.json to add `CHROMA_MODE=persistent`**

Use the `Edit` tool on `C:\Users\radmo\.claude-mem\settings.json`. The exact edit depends on the current content shape — two cases:

**Case A: file is `{}`** — replace with:
```json
{
  "CLAUDE_MEM_CHROMA_MODE": "persistent"
}
```

**Case B: file already has keys** — add a new line `"CLAUDE_MEM_CHROMA_MODE": "persistent",` after the opening `{`. Verify trailing-comma correctness with a JSON parser:
```bash
python -c "import json; json.load(open('/c/Users/radmo/.claude-mem/settings.json'))" && echo OK
```
Expected: `OK`. If parse error, fix the JSON before continuing.

- [ ] **Step 3: Restart the worker**

⚠ **CLI MUTATION** — `npx claude-mem restart` stops and restarts the worker process. Authorized by this plan.

Run:
```bash
npx claude-mem restart
```
Expected: stdout shows "Stopping worker..." → "Starting worker..." → "Worker started on http://127.0.0.1:37777".

If you see "Worker is not running" before stop, that's fine — `restart` is `stop || true` then `start`.

- [ ] **Step 4: Wait for worker to be healthy again**

Run (poll up to 30 seconds):
```bash
for i in 1 2 3 4 5 6 7 8 9 10; do
  curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:37777/api/health 2>/dev/null && break
  sleep 3
done
```
Expected: ends with `200`.

If still non-200 after 30s → STOP. Roll back settings.json from snapshot (`cp /c/Users/radmo/.claude/plans/backups/claude-mem-settings-2026-05-24.json ~/.claude-mem/settings.json`), `npx claude-mem restart`, then flag to user.

- [ ] **Step 5: Probe chroma deep-status**

Run:
```bash
curl -sS "http://127.0.0.1:37777/api/chroma/status?deep=1"
```
Look at the response JSON. Two possible outcomes:

**Outcome A (HAPPY PATH):**
```json
{"enabled":true,"mode":"persistent","connected":true, ...}
```
→ keep persistent mode, **skip Task 4, proceed to Task 5**.

**Outcome B (FALL-BACK PATH):** `"connected":false` OR `"error"` field present OR `"backoff"` field non-zero:
→ persistent mode also unhealthy on Windows. **Proceed to Task 4** to disable chroma.

- [ ] **Step 6: Confirm with one observation sync test (only if Outcome A)**

If Outcome A from Step 5, sanity-check that the per-observation chroma errors have stopped:

Run:
```bash
curl -sS "http://127.0.0.1:37777/api/admin/doctor" | grep -i "chroma"
```
Expected: no `"error"`, no `"backoff"` indicators in chroma block.

Record the outcome (A or B) — you'll need it for Task 5.

---

## Task 4: Track A2 Fallback — disable chroma (CONDITIONAL on Task 3 Outcome B only)

**Skip this entire task if Task 3 Step 5 reported Outcome A.**

**Files:**
- Modify: `~/.claude-mem/settings.json` (replace `CHROMA_MODE` with `CHROMA_ENABLED=false`)

- [ ] **Step 1: Edit settings.json — remove `CHROMA_MODE`, add `CHROMA_ENABLED=false`**

Use the `Edit` tool on `C:\Users\radmo\.claude-mem\settings.json`:
- Remove the `"CLAUDE_MEM_CHROMA_MODE": "persistent",` line added in Task 3 Step 2
- Add the line `"CLAUDE_MEM_CHROMA_ENABLED": "false",`

Result fragment (assuming previously empty `{}`):
```json
{
  "CLAUDE_MEM_CHROMA_ENABLED": "false"
}
```

Validate JSON:
```bash
python -c "import json; json.load(open('/c/Users/radmo/.claude-mem/settings.json'))" && echo OK
```
Expected: `OK`.

- [ ] **Step 2: Restart worker and wait for health**

⚠ **CLI MUTATION** — authorized by this plan.

Run:
```bash
npx claude-mem restart
```
Then poll:
```bash
for i in 1 2 3 4 5 6 7 8 9 10; do
  curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:37777/api/health 2>/dev/null && break
  sleep 3
done
```
Expected: ends with `200`.

- [ ] **Step 3: Confirm chroma is now disabled**

Run:
```bash
curl -sS http://127.0.0.1:37777/api/chroma/status
```
Expected: `{"enabled":false}` or equivalent indicating disabled.

- [ ] **Step 4: Confirm per-observation sync errors stopped**

Run:
```bash
curl -sS http://127.0.0.1:37777/api/admin/doctor
```
Expected: no chroma backoff/error in the response.

- [ ] **Step 5: Confirm `/api/search/observations` still works (the chroma-free search path)**

Run:
```bash
curl -sS "http://127.0.0.1:37777/api/search/observations?q=BLACS&limit=3"
```
Expected: JSON with at least 1 result row. If 200 with an empty array, that's OK (FTS5 may not have indexed the term). 5xx is NOT OK — investigate.

---

## Task 5: Apply combined Track A3 + B1 + B2 settings

**Files:**
- Modify: `~/.claude-mem/settings.json` (final shape)

This task writes the canonical combined block from the spec. The exact JSON depends on Task 3 outcome.

- [ ] **Step 1: Replace `settings.json` with the combined block**

**If Task 3 Outcome A (chroma persistent is healthy):**

Use the `Write` tool to set `C:\Users\radmo\.claude-mem\settings.json` to exactly:

```json
{
  "CLAUDE_MEM_RUNTIME": "worker",
  "CLAUDE_MEM_CONTEXT_OBSERVATIONS": "10",
  "CLAUDE_MEM_CONTEXT_FULL_COUNT": "2",
  "CLAUDE_MEM_CONTEXT_SESSION_COUNT": "3",
  "CLAUDE_MEM_CONTEXT_OBSERVATION_TYPES": "bugfix,decision",
  "CLAUDE_MEM_CONTEXT_SHOW_LAST_SUMMARY": "true",
  "CLAUDE_MEM_SKIP_TOOLS": "ListMcpResourcesTool,SlashCommand,Skill,TodoWrite,AskUserQuestion,Grep,Glob,WebFetch,WebSearch,REPL",
  "CLAUDE_MEM_FOLDER_CLAUDEMD_ENABLED": "true",
  "CLAUDE_MEM_CHROMA_MODE": "persistent"
}
```

**If Task 3 Outcome B → Task 4 ran (chroma disabled):**

Use the `Write` tool to set `C:\Users\radmo\.claude-mem\settings.json` to exactly:

```json
{
  "CLAUDE_MEM_RUNTIME": "worker",
  "CLAUDE_MEM_CONTEXT_OBSERVATIONS": "10",
  "CLAUDE_MEM_CONTEXT_FULL_COUNT": "2",
  "CLAUDE_MEM_CONTEXT_SESSION_COUNT": "3",
  "CLAUDE_MEM_CONTEXT_OBSERVATION_TYPES": "bugfix,decision",
  "CLAUDE_MEM_CONTEXT_SHOW_LAST_SUMMARY": "true",
  "CLAUDE_MEM_SKIP_TOOLS": "ListMcpResourcesTool,SlashCommand,Skill,TodoWrite,AskUserQuestion,Grep,Glob,WebFetch,WebSearch,REPL",
  "CLAUDE_MEM_FOLDER_CLAUDEMD_ENABLED": "true",
  "CLAUDE_MEM_CHROMA_ENABLED": "false"
}
```

The difference is the last key only.

- [ ] **Step 2: Validate JSON**

Run:
```bash
python -c "import json; d=json.load(open('/c/Users/radmo/.claude-mem/settings.json')); print(len(d), 'keys')"
```
Expected: `9 keys`.

- [ ] **Step 3: Diff against snapshot for sanity**

Run:
```bash
diff /c/Users/radmo/.claude/plans/backups/claude-mem-settings-2026-05-24.json ~/.claude-mem/settings.json
```
Expected: the diff is non-empty (file changed) AND shows the new keys being added/changed (no unrelated deletions).

---

## Task 6: Restart worker, then restart Claude Code

**Files:** (none — process state)

- [ ] **Step 1: Restart the worker so settings take effect**

⚠ **CLI MUTATION** — authorized.

Run:
```bash
npx claude-mem restart
```
Then poll health:
```bash
for i in 1 2 3 4 5 6 7 8 9 10; do
  curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:37777/api/health 2>/dev/null && break
  sleep 3
done
```
Expected: ends with `200`.

- [ ] **Step 2: Verify new settings are loaded in the worker**

Run:
```bash
curl -sS http://127.0.0.1:37777/api/settings | grep -E "CONTEXT_OBSERVATIONS|FOLDER_CLAUDEMD|SKIP_TOOLS|SESSION_COUNT"
```
Expected: see `"10"`, `"3"`, `"true"`, and the extended SKIP_TOOLS list with `Grep,Glob,WebFetch,WebSearch,REPL` present.

If a key is missing or shows the default value, the worker did not reload — re-run Step 1.

- [ ] **Step 3: User restarts Claude Code (manual)**

The MCP tool registration and the SessionStart hook content both load when Claude Code starts. After worker restart, **the user must restart Claude Code** for changes to take full effect in their interactive session.

Prompt the user:

> "Worker has been restarted with the new claude-mem settings. To register the newly enabled MCP tools and load the new SessionStart hook content in your interactive session, **please quit and reopen Claude Code (or the VS Code window hosting it) now.** When you're back, reply 'ready' and we'll run the final verification."

Wait for user 'ready' response before proceeding.

---

## Task 7: Final verification — five health checks

**Files:**
- Create: `C:\Users\radmo\.claude\plans\backups\claude-mem-injection-size-after-2026-05-24.txt` (compare against baseline)

- [ ] **Step 1: `/api/admin/doctor` overall health**

Run:
```bash
curl -sS http://127.0.0.1:37777/api/admin/doctor
```
Expected: response contains `"supervisor":` (or equivalent) with running state, processes alive, `"envClean": true`.

If `envClean: false` → some `CLAUDE_MEM_*` env vars are set in the shell environment and are overriding settings.json. Investigate which (`env | grep CLAUDE_MEM`) and decide whether to unset them. Out of scope for this plan unless blocking.

- [ ] **Step 2: Injection size shrunk**

Run:
```bash
curl -sS "http://127.0.0.1:37777/api/context/inject?project=labscript-suite" | wc -c > /c/Users/radmo/.claude/plans/backups/claude-mem-injection-size-after-2026-05-24.txt
cat /c/Users/radmo/.claude/plans/backups/claude-mem-injection-size-after-2026-05-24.txt
```
Expected: a number **< 5000** (per spec target).

Compare to baseline:
```bash
echo "Before: $(cat /c/Users/radmo/.claude/plans/backups/claude-mem-injection-size-baseline-2026-05-24.txt)"
echo "After:  $(cat /c/Users/radmo/.claude/plans/backups/claude-mem-injection-size-after-2026-05-24.txt)"
```
Expected: After is roughly 15-25% of Before (e.g., 21000 → 3000-5000).

If the After number is still > 8000, the settings did not apply — re-check `/api/settings` against the canonical block in Task 5 Step 1. Possible cause: env-var override (Step 1's `envClean: false`).

- [ ] **Step 3: MCP enabled**

Run:
```bash
curl -sS http://127.0.0.1:37777/api/mcp/status
```
Expected: `"enabled":true`.

- [ ] **Step 4: Chroma in expected state**

Run:
```bash
curl -sS "http://127.0.0.1:37777/api/chroma/status?deep=1"
```
Expected (Task 3 Outcome A): `"connected":true,"mode":"persistent"`.
Expected (Task 4 fallback ran): `"enabled":false`.

- [ ] **Step 5: DB still growing (capture didn't break)**

Run:
```bash
curl -sS http://127.0.0.1:37777/api/stats
```
Expected: JSON with `observations` (or similar) count ≥ 928 (the pre-change count from the spec). The count may not have grown yet if no tool calls have run since restart — that's fine, we'll re-check at the audit step.

- [ ] **Step 6: Sanity — fire one observation, confirm capture path works**

In this Claude Code session, do ONE deliberate file read of a small file the user hasn't touched in days, e.g.:

```
Read tool on c:/Users/radmo/labscript-suite/CLAUDE.md (limit 5 lines)
```

Then wait 5 seconds and run:
```bash
curl -sS "http://127.0.0.1:37777/api/observations?limit=3" | grep -oE '"created_at":"[^"]+"' | head -3
```
Expected: at least one row with a `created_at` timestamp within the last minute.

If no new row appears within 60 seconds → capture pipeline is broken; investigate hooks (`tail ~/.claude-mem/logs/worker.log`).

- [ ] **Step 7: Sanity — folder CLAUDE.md is now being referenced**

Run:
```bash
curl -sS "http://127.0.0.1:37777/api/observations?limit=20" | grep -i "CLAUDE.md"
```
Expected: at least one observation references a folder-level `CLAUDE.md`. If none yet (FOLDER_CLAUDEMD_ENABLED works post-session, not on the fly), defer this check to the 2-3 session audit.

---

## Task 8: Document the CLI install trap

**Files:**
- Modify: `c:\Users\radmo\labscript-suite\CLAUDE.md` (one bullet added to "Do NOT Flag These" section)
- Modify: `C:\Users\radmo\.claude\projects\c--Users-radmo-labscript-suite\memory\MEMORY.md` (one line added)

- [ ] **Step 1: Read the existing CLAUDE.md "Do NOT Flag These" section**

Use the `Read` tool on `c:\Users\radmo\labscript-suite\CLAUDE.md`, locate the section starting with `## Do NOT Flag These`. The existing third bullet is:

```
- **`npx claude-mem status` saying "Worker is not running"** — known CLI bug (unwritten `.worker.pid`). Ground truth: `netstat -ano | grep 37777` LISTENING + `curl http://127.0.0.1:37777/api/health`
```

- [ ] **Step 2: Append a new bullet immediately after that one**

Use the `Edit` tool to add this bullet directly after the `npx claude-mem status` bullet:

```
- **Never run bare `npx claude-mem` or with unknown flags** — defaults to install (v13.3.0 bundle line 9943). Only `-h/--help/-v/--version` are whitelisted at top level; `install --help` ALSO runs the installer. Safe diagnostics: `npx claude-mem version`, `search <query>`, `status` (unreliable), or REST API at `http://127.0.0.1:37777/api/admin/doctor`.
```

- [ ] **Step 3: Read native memory MEMORY.md around line 44**

Use the `Read` tool on `C:\Users\radmo\.claude\projects\c--Users-radmo-labscript-suite\memory\MEMORY.md` with `offset=40, limit=10`.

There is an existing generic bullet at line 44 in the `## Workflow Lessons` section:

```
- **Unknown CLI subcommands can side-effect in non-TTY** — `--help`/`status` probes on unfamiliar tools may run the real action when stdin is not a TTY (this session: `npx claude-mem install --help` ran the installer). Confirm help-safety or sandbox the probe first.
```

We will replace it with a sharper, citation-bearing version that points to the existing reference file `reference_claude-mem-cli-surface.md` (already at `C:\Users\radmo\.claude\projects\c--Users-radmo-labscript-suite\memory\reference_claude-mem-cli-surface.md`).

- [ ] **Step 4: Replace the line 44 bullet with the sharper version**

Use the `Edit` tool on `C:\Users\radmo\.claude\projects\c--Users-radmo-labscript-suite\memory\MEMORY.md`.

`old_string`:
```
- **Unknown CLI subcommands can side-effect in non-TTY** — `--help`/`status` probes on unfamiliar tools may run the real action when stdin is not a TTY (this session: `npx claude-mem install --help` ran the installer). Confirm help-safety or sandbox the probe first.
```

`new_string`:
```
- [claude-mem CLI install-trap + safe-command map](reference_claude-mem-cli-surface.md) — `npx claude-mem` with no args, or with any flag not in `-h/--help/-v/--version`, dispatches to `install` (v13.3.0 bundle line 9943). `install --help` ALSO runs the installer. Generalization for any unfamiliar CLI: confirm `--help`-safety against the source, or sandbox; never probe in non-TTY/agent context.
```

This keeps the generalization (the wider lesson about unfamiliar CLI probes) AND adds the concrete claude-mem citation + link.

- [ ] **Step 5: Commit the labscript-suite CLAUDE.md change**

Run:
```bash
cd /c/Users/radmo/labscript-suite
git add CLAUDE.md
git status
```
Expected: `CLAUDE.md` shown under "Changes to be committed", nothing else.

Then:
```bash
git diff --cached CLAUDE.md
```
Expected: the diff shows exactly the new bullet from Step 2 added, no unrelated changes.

Then commit:
```bash
git commit -m "docs(CLAUDE.md): add claude-mem CLI install-trap rule to 'Do NOT Flag These'

The bare-args/unknown-flag → install behaviour (v13.3.0 bundle line 9943) bit us
this week — \`npx claude-mem install --help\` ran the real installer. Adding
the safety rule alongside the existing \`status\` bullet so future sessions
don't repeat the same mistake.

Source: ~/.claude/projects/c--Users-radmo-labscript-suite/memory/reference_claude-mem-cli-surface.md"
```
Expected: commit created.

**Do NOT push.** The CLAUDE.md instructions explicitly say "Commit to each repo separately. Do not push without asking."

---

## Task 9: Stub three Track C follow-up plans

Track C is **not executed in this plan** — these are placeholder plan files for future writing-plans sessions, so the deferred work doesn't get lost.

**Files:**
- Create: `c:\Users\radmo\labscript-suite\.claude\docs\superpowers\plans\2026-05-24-pathfinder-architectural-audit.md`
- Create: `c:\Users\radmo\labscript-suite\.claude\docs\superpowers\plans\2026-05-24-knowledge-agent-corpora.md`
- Create: `c:\Users\radmo\labscript-suite\.claude\docs\superpowers\plans\2026-05-24-make-plan-vendor-hardware-adoption.md`

- [ ] **Step 1: Stub the pathfinder audit plan**

Use the `Write` tool to create `c:\Users\radmo\labscript-suite\.claude\docs\superpowers\plans\2026-05-24-pathfinder-architectural-audit.md` with content:

```markdown
# Pathfinder Architectural Duplication Audit — STUB (Track C1)

> **STATUS:** Not yet planned. This is a placeholder spawned by `2026-05-24-claude-mem-tuning.md` Task 9. Run `superpowers:writing-plans` against this stub when ready to execute.

**Goal:** Run claude-mem's `pathfinder` skill against the active code surfaces of this lab's labscript fork to surface architectural duplications — the kind of thing that would have caught the two-RemoteControl-trees situation automatically.

**Target paths:**
- `c:\Users\radmo\labscript-suite\userlib\user_devices\`
- `c:\Users\radmo\labscript-suite\labscript-devices\labscript_devices\`
- `c:\Users\radmo\labscript-suite\blacs\`

**Expected output:** `PATHFINDER-YYYY-MM-DD/` directory with:
- per-feature flowcharts
- duplication report (pairs of files/functions with overlapping responsibility)
- unified-architecture proposal for the worst offenders

**Source spec:** [`.claude/docs/superpowers/specs/2026-05-24-claude-mem-tuning-design.md`](../specs/2026-05-24-claude-mem-tuning-design.md) — Track C1
```

- [ ] **Step 2: Stub the knowledge-agent corpora plan**

Use the `Write` tool to create `c:\Users\radmo\labscript-suite\.claude\docs\superpowers\plans\2026-05-24-knowledge-agent-corpora.md` with content:

```markdown
# Knowledge-Agent Focused Corpora — STUB (Track C2)

> **STATUS:** Not yet planned. This is a placeholder spawned by `2026-05-24-claude-mem-tuning.md` Task 9. Run `superpowers:writing-plans` against this stub when ready to execute.

**Goal:** Build three claude-mem `knowledge-agent` corpora targeting recurring lab topics, so `prime_corpus` calls at session start give focused context instead of generic injection.

**Corpora to build:**

1. **`post-exp-lifecycle`** — covers:
   - BLACS state machine modes (`MODE_TRANSITION_TO_POST_EXP=16`, `MODE_POST_EXP=32`)
   - `post_experiment` vs `transition_to_manual` fork divergence
   - Per-shot teardown rules (see `docs/blacs-state-machine.md`)
   - The ~80 ms back-compat probe for missing `post_experiment`

2. **`zmq-v2-protocol`** — covers:
   - Protocol envelope (REQ-REP + PUB-SUB)
   - REJECTED contract semantics
   - Transport handling per `docs/remotecontrol-zmq-protocol.md`
   - Recent v2 cutover commits

3. **`raxcollab-fork-divergence`** — covers:
   - NI_DAQmx latched lines behavior
   - Two-RemoteControl-trees situation
   - All `our fork is ground truth` items from `CLAUDE.md`

**Source spec:** [`.claude/docs/superpowers/specs/2026-05-24-claude-mem-tuning-design.md`](../specs/2026-05-24-claude-mem-tuning-design.md) — Track C2
```

- [ ] **Step 3: Stub the make-plan adoption plan**

Use the `Write` tool to create `c:\Users\radmo\labscript-suite\.claude\docs\superpowers\plans\2026-05-24-make-plan-vendor-hardware-adoption.md` with content:

```markdown
# `make-plan` Adoption for Vendor-Hardware Work — STUB (Track C3)

> **STATUS:** Not yet planned. This is a placeholder spawned by `2026-05-24-claude-mem-tuning.md` Task 9. Run `superpowers:writing-plans` against this stub when ready to execute.

**Goal:** Replace `superpowers:writing-plans` with claude-mem's `make-plan` skill for **vendor-hardware work specifically** (Matisse, BigSky, HighFinesse, NuVu, NI). `make-plan` mandates a Phase 0 "documentation discovery" step, which addresses the failure mode captured in `feedback_research-rationale-not-guess.md` (the lab agent guessing at vendor APIs instead of reading the manual).

**Scope of change:**
- Add a routing rule (in `.claude/rules/` or via the agent-workflow skill) that says: "For tasks touching `userlib/user_devices/Matisse*`, `BigSky*`, `LaserLockDevice/`, `NuvuCamera/`, or `NI_*`, invoke `make-plan` instead of `writing-plans`."
- Do NOT replace `writing-plans` globally — for code-only work it's still the right choice.

**Acceptance criteria:**
- Next time a vendor-hardware-touching task runs through plan-mode, the assistant invokes `make-plan` and produces a Phase 0 discovery section before any task definition.

**Source spec:** [`.claude/docs/superpowers/specs/2026-05-24-claude-mem-tuning-design.md`](../specs/2026-05-24-claude-mem-tuning-design.md) — Track C3
```

- [ ] **Step 4: Verify stub files exist**

Run:
```bash
ls -la /c/Users/radmo/labscript-suite/.claude/docs/superpowers/plans/2026-05-24-*.md
```
Expected: 4 files listed (this plan + 3 stubs).

- [ ] **Step 5: Do NOT commit the stub plans yet**

The stub plans are not committed because they're TBD by design — they'll be filled in by their own `writing-plans` sessions. Adding empty-stub plans to git pollutes history. Leave them as untracked / unstaged files. The user can decide later whether to commit them as documentation of intent or to skip the commit until each is implemented.

If the user wants them committed as intent documentation:
```bash
cd /c/Users/radmo/labscript-suite
git add .claude/docs/superpowers/plans/2026-05-24-pathfinder-architectural-audit.md
git add .claude/docs/superpowers/plans/2026-05-24-knowledge-agent-corpora.md
git add .claude/docs/superpowers/plans/2026-05-24-make-plan-vendor-hardware-adoption.md
git commit -m "docs(plans): stub Track C follow-up plans for claude-mem tuning

See .claude/docs/superpowers/specs/2026-05-24-claude-mem-tuning-design.md
Track C — these are spawned as placeholders by Task 9 of the tuning plan
so the follow-up work doesn't get lost. Each will be filled out by its
own writing-plans session."
```

**Default behavior: leave uncommitted. Ask the user before committing.**

---

## Task 10: 2-3 session audit (deferred — user-driven)

This task **cannot execute now** — it requires letting the new settings run through 2-3 real working sessions, then reviewing whether the injection content was actually useful.

**Files:** (none — observation-only)

- [ ] **Step 1: Define the audit window**

After Task 7 completes, mark today as audit day 0. Set a reminder to audit on day 3 (typically the next 2-3 normal working sessions of mixed BLACS / sequence / analysis work).

- [ ] **Step 2: Audit checklist — run this at day 3**

Open a normal working session. Within that session, evaluate:

**A. Did SessionStart injection get cited?**
- Look at the session-start banner content. Did the assistant reference any of those observations during the work?
- If YES: keep `CONTEXT_OBSERVATIONS=10`.
- If NO across all 2-3 audit sessions: drop to `CONTEXT_OBSERVATIONS=5`. If still no after another 2-3 sessions: drop to `CONTEXT_OBSERVATIONS=0` (rev 3 Phase 2 escalation; per spec Implementation Order Step 7).

**B. Is smart-explore reachable?**

In a normal session, try:
```
mcp__claude_mem__smart_search(query="post_experiment", path=".")
```
Expected: structured symbol results.

If "tool not found" → MCP didn't register at Claude Code startup. Re-enable via Task 2 Step 2 again and restart Claude Code.

**C. Is folder-local CLAUDE.md showing up in new observations?**

Run:
```bash
curl -sS "http://127.0.0.1:37777/api/observations?limit=50&since=$(date -d '3 days ago' +%s)" | grep -i "GUIs/BigSkyControl/CLAUDE.md\|GUIs/HF_Locking/CLAUDE.md\|GUIs/rastering/CLAUDE.md"
```
Expected: at least one match.

If empty after 3 days of touching the GUIs/ folders → `FOLDER_CLAUDEMD_ENABLED` is not actually picking them up. Investigate `~/.claude-mem/logs/worker.log` for folder-md generation messages.

**D. Did extending SKIP_TOOLS lose useful recall?**

Recall test: did the assistant ever need to look up a REPL output or a WebFetch result from the last few sessions and find nothing? If so, the SKIP_TOOLS extension was too aggressive. Trim `REPL` and `WebFetch` from the list (keep `Grep,Glob,WebSearch`).

**E. Is per-prompt cost now in target range?**

```bash
curl -sS "http://127.0.0.1:37777/api/context/inject?project=labscript-suite" | wc -c
```
Expected: still < 5000 (settings shouldn't drift between sessions, but verify).

- [ ] **Step 3: Record audit outcome**

Append findings to `c:\Users\radmo\labscript-suite\notes\` as a dated lab note (the project's existing convention — see `notes/2026-05-23_ZMQ-v2-Cutover-Shipped.html` and `notes/2026-05-22_Matisse-External-Locking-Architecture-Investigation.html` for format precedent). Name it `2026-05-XX_claude-mem-tuning-audit.html` where XX is the audit day.

If any of A-D failed → that becomes the trigger for a rev 5 spec OR a settings rollback (Task 11 below).

---

## Task 11: Rollback procedure (if needed at any point)

**Files:**
- Restore: `~/.claude-mem/settings.json` from snapshot

These steps are **not part of the linear plan execution** — they're the escape hatch if Task 7 verification fails or the day-3 audit reveals a regression.

- [ ] **Step R1: Restore settings.json from snapshot**

Run:
```bash
cp /c/Users/radmo/.claude/plans/backups/claude-mem-settings-2026-05-24.json ~/.claude-mem/settings.json
```
Expected: settings restored to pre-change state.

- [ ] **Step R2: Re-disable MCP via REST POST (if reverting Track A1)**

Run:
```bash
curl -sS -X POST http://127.0.0.1:37777/api/mcp/toggle \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```
Verify: `curl http://127.0.0.1:37777/api/mcp/status` → `"enabled":false`.

- [ ] **Step R3: Restart worker**

⚠ CLI MUTATION — authorized in rollback context.

Run:
```bash
npx claude-mem restart
```

- [ ] **Step R4: Revert CLAUDE.md change (if reverting documentation)**

Run:
```bash
cd /c/Users/radmo/labscript-suite
git revert HEAD --no-edit
# Or, if not yet pushed and you'd rather erase from history:
# git reset --hard HEAD~1
```
Note: `git reset --hard` is destructive; prefer `revert`. Ask user before doing either.

- [ ] **Step R5: Confirm rollback healthy**

Run:
```bash
curl -sS http://127.0.0.1:37777/api/admin/doctor
curl -sS http://127.0.0.1:37777/api/settings | grep -E "CONTEXT_OBSERVATIONS|FOLDER_CLAUDEMD"
```
Expected: settings match the pre-change snapshot, doctor is healthy.

Data note: **The claude-mem DB and all observations are never modified by this plan or its rollback.** No data loss.

---

## Self-Review Summary

**Spec coverage:**
- Spec Track A1 (enable MCP) → Task 2 ✓
- Spec Track A2 (chroma) → Task 3 (persistent attempt) + Task 4 (fallback) ✓
- Spec Track A3 (folder CLAUDE.md) → Task 5 (included in combined settings) ✓
- Spec Track B1 (injection tuning) → Task 5 ✓
- Spec Track B2 (capture-side SKIP_TOOLS) → Task 5 ✓
- Spec Implementation Order Step 1 (snapshot) → Task 1 ✓
- Spec Implementation Order Step 5 (Claude Code restart) → Task 6 Step 3 ✓
- Spec Implementation Order Step 6 (verify) → Task 7 ✓
- Spec Implementation Order Step 7 (2-3 session audit) → Task 10 ✓
- Spec Implementation Order Step 8 (Track C follow-ups) → Task 9 ✓
- Spec Rollback Procedure → Task 11 ✓
- Spec CLI Safety Addendum (add rule to MEMORY.md) → Task 8 ✓ (extended to also update labscript-suite CLAUDE.md)

**Type/path consistency:**
- All curl URLs use `http://127.0.0.1:37777`
- All settings.json paths use `~/.claude-mem/settings.json` (with cross-platform variant `C:\Users\radmo\.claude-mem\settings.json` where Windows-only)
- Backup directory path stable: `/c/Users/radmo/.claude/plans/backups/` (bash) ≡ `C:\Users\radmo\.claude\plans\backups\` (Windows)
- All "restart worker" steps consistently use `npx claude-mem restart` flagged with ⚠ CLI MUTATION

**Known plan-internal trade-offs:**
- Task 9 leaves stub plans uncommitted by default — see Task 9 Step 5 for the rationale and the opt-in commit command
- Task 8 commits CLAUDE.md immediately because it's a tested, ready-to-use rule
- Task 10 is deferred-execution; the executing agent must surface this to the user as "this task waits for real-world sessions"

---

## Execution Order Summary (quick reference)

```
Task 0  → preflight worker healthy
Task 1  → snapshot settings + baseline injection size
Task 2  → POST /api/mcp/toggle enabled=true
Task 3  → settings.json += CHROMA_MODE=persistent ; restart ; check chroma deep-status
            ├── Outcome A (healthy)  → skip Task 4, go to Task 5
            └── Outcome B (failed)   → Task 4
Task 4  → (conditional) settings.json := CHROMA_ENABLED=false ; restart ; verify
Task 5  → Write final combined settings.json (9 keys)
Task 6  → npx claude-mem restart ; user restarts Claude Code ; user says 'ready'
Task 7  → 5 health curls + 2 sanity probes
Task 8  → edit labscript-suite/CLAUDE.md + native MEMORY.md ; commit CLAUDE.md
Task 9  → stub 3 Track C plans (uncommitted by default)
Task 10 → audit on day 3 (deferred — user-driven)
Task 11 → rollback (escape hatch, not in linear flow)
```
