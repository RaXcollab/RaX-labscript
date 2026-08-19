# Claude-mem Tuning — Design Spec (2026-05-24, rev 4)

## Reframe (carried from rev 3)

Half the apparent "bloat" was unconfigured features failing silently. Half the apparent "cost" was knobs we hadn't seen.

**New dominant finding (rev 4):** `UserPromptSubmit → session-init` injects the same ~21k-token context block on **every user prompt**, not just session start. Daily cost dominates session-start cost. With 30 prompts/day → **~630k tokens/day** injected into the assistant just from this one hook.

Rev 4 organizes into three tracks:
- **Track A — Finish initializing** (carries from rev 3): enable MCP, verify chroma persistent mode, enable folder-local CLAUDE.md
- **Track B — Tune injection AND capture** (extends rev 3): the original context env vars PLUS extended `SKIP_TOOLS` to drop 40-60% of PostToolUse fires
- **Track C — Follow-up plans to schedule** (NEW): pathfinder audit, knowledge-agent corpora, `make-plan` adoption for vendor-hardware work — captured as plan IDs to write later, NOT executed here

## Problem (updated)

Across 7 days of logs and live measurement:
- `UserPromptSubmit` fires every prompt → ~21k tokens per prompt → ~630k tokens/day (30 prompts)
- `SessionStart` matcher `startup|clear|compact` adds another 22k per `/clear` or compact
- `PostToolUse` matcher `*` fires ~1,326 times/day at this lab → ~9M Haiku discovery tokens/day (~$1.50/day on subscription tier)
- 0 organic searches in normal work, 0 user back-references in 132 prompts
- The 912-obs DB has not been cited in normal reasoning; native MEMORY.md is the load-bearing memory layer
- **Chroma broken**: every observation hits chroma sync and fails (`MCP error -32000: Connection closed`). Every `/api/search/by-*` endpoint returns 500. FTS5 fallback was removed in v12 cleanup. Background error spam continuous.
- **MCP toggled off** → `smart-explore` skill silently broken since whenever it was disabled

## Hard Constraints (user-stated)

Preserve these skills:
- `learn-codebase` — no claude-mem dependency
- `smart-explore` — REQUIRES MCP enabled (Track A1) and worker daemon
- `babysit` — no claude-mem dependency

Worker daemon stays running in every phase.

## Verified runtime facts (`curl http://127.0.0.1:37777/api/settings`)

- `CLAUDE_MEM_MODEL=claude-haiku-4-5-20251001` (Haiku confirmed; no swap needed)
- `CLAUDE_MEM_TIER_ROUTING_ENABLED=true`, `TIER_SIMPLE_MODEL=haiku` (already cheap)
- `CLAUDE_MEM_SEMANTIC_INJECT=false` (off by default)
- `CLAUDE_MEM_MODE=code` (default; `code--chill` exists but rejected — see Alt B)
- MCP `enabled=false` (toggled off — fix in Track A1)
- Chroma `unhealthy` (fix or disable — Track A2)
- 928 observations, 6.5M cumulative discovery tokens over 5 days
- Plugin v13.3.0 now installed alongside v13.2.0 (accidental install collateral; v13.3.0 is the active version)

## Track A — Finish Initializing

### A1. Enable MCP server

```bash
curl -X POST http://127.0.0.1:37777/api/mcp/toggle \
  -H "Content-Type: application/json" -d '{"enabled": true}'
```
Verify:
```bash
curl http://127.0.0.1:37777/api/mcp/status
# expect: {"enabled":true}
```
Effect: registers `smart_search`/`smart_outline`/`smart_unfold` + 18 other MCP tools. Smart-explore skill becomes functional. Cost: ~2k tokens of tool defs in system prompt per session.

### A2. Resolve chroma — test persistent mode, fall back to disable

Chroma is currently in retry-loop on every observation. Two failure points: per-observation sync fails, AND all `/api/search/by-*` endpoints 500. Resolve before further tuning.

Test sequence:
1. Add `"CLAUDE_MEM_CHROMA_MODE": "persistent"` to `~/.claude-mem/settings.json`
2. `npx claude-mem restart`
3. `curl http://127.0.0.1:37777/api/chroma/status?deep=1`
4. If `connected: true` → keep `persistent`. Semantic search and `/api/search/by-*` come back online.
5. If still unhealthy → set `"CLAUDE_MEM_CHROMA_ENABLED": "false"`. Lose `/api/search/by-*` endpoints. **Keep** `/api/search/observations`, `/api/context/recent`, `/api/observations/by-file` (all chroma-free). Stop the per-observation retry loop.

### A3. Enable folder-local CLAUDE.md injection

You have 5 folder-local CLAUDE.md files (labscript-suite + 4 GUIs). Currently `FOLDER_CLAUDEMD_ENABLED=false`. Set true.

```json
"CLAUDE_MEM_FOLDER_CLAUDEMD_ENABLED": "true"
```
Observations begin referencing folder-local CLAUDE.md content. Verify by reading a file in `GUIs/BigSkyControl/` and checking `curl /api/observations | grep BigSkyControl/CLAUDE.md`.

## Track B — Tune Injection AND Capture

Two layers, both via `~/.claude-mem/settings.json`.

### B1. Injection-side tuning (the headline)

Per-prompt injection currently ~21k tokens. With these settings → ~3-5k:

```json
{
  "CLAUDE_MEM_CONTEXT_OBSERVATIONS": "10",
  "CLAUDE_MEM_CONTEXT_FULL_COUNT": "2",
  "CLAUDE_MEM_CONTEXT_SESSION_COUNT": "3",
  "CLAUDE_MEM_CONTEXT_OBSERVATION_TYPES": "bugfix,decision",
  "CLAUDE_MEM_CONTEXT_SHOW_LAST_SUMMARY": "true"
}
```

Rationale: `SESSION_COUNT=3` (parallel-session bridging — your stated value). `OBSERVATION_TYPES="bugfix,decision"` filters out noise discoveries. `SHOW_LAST_SUMMARY=true` keeps the high-value cross-session bridge. `FULL_COUNT=2` expands two obs to full narrative for richer signal.

### B2. Capture-side trim (NEW — from hook agent finding)

Default `SKIP_TOOLS` skips 5 internal tools. Extend to skip 5 more high-volume read-only tools:

```json
"CLAUDE_MEM_SKIP_TOOLS": "ListMcpResourcesTool,SlashCommand,Skill,TodoWrite,AskUserQuestion,Grep,Glob,WebFetch,WebSearch,REPL"
```

Effect: drops 40-60% of the 1,326 daily PostToolUse fires. Compression spend halves. DB growth slows. Higher signal per observation (only Read/Edit/Bash/etc. — the actual work tools).

Risk: lose recall of REPL outputs and web fetches. Mitigation: these are usually ephemeral (REPL probes, doc fetches); the durable conclusion lands in a non-skipped Edit anyway.

### B3. Folder CLAUDE.md (set in A3, listed here for the combined settings block)

### Combined Track A+B settings.json

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

If A2 falls back, change `CHROMA_MODE` to `local` and add `"CLAUDE_MEM_CHROMA_ENABLED": "false"`.

## Track C — Follow-up Plans (NOT executed here)

Captured as future plan IDs. Each is a separate writing-plans session.

### C1. `pathfinder` architectural duplication audit
Run `pathfinder` against `userlib/user_devices/` + `labscript-devices/labscript_devices/` + `blacs/` to surface duplications (would have caught the two-RemoteControl-trees automatically). Output: `PATHFINDER-YYYY-MM-DD/` with feature flowcharts + duplication report + unified proposal.

### C2. `knowledge-agent` focused corpora
Build 3 corpora targeting recurring topics:
- `post-exp-lifecycle` — BLACS lifecycle, post_experiment vs T2M, fork divergences
- `zmq-v2-protocol` — protocol envelope, REJECTED contract, transport handling
- `raxcollab-fork-divergence` — NI_DAQmx latched lines, two-RemoteControl-trees, etc.

After build, `prime_corpus` at relevant session starts to give focused context.

### C3. `make-plan` adoption for vendor-hardware work
Replace `writing-plans` with `make-plan` for Matisse/BigSky/HighFinesse work specifically. `make-plan` mandates Phase 0 documentation discovery — addresses the failure mode in `feedback_research-rationale-not-guess.md`.

## Verification (uses `/api/admin/doctor`, not broken CLI)

`npx claude-mem status` is unreliable (known bug). Use the worker REST API:

```bash
# Worker + SDK + processes healthy
curl http://127.0.0.1:37777/api/admin/doctor
# expect: supervisor running, processes alive, envClean: true

# Live preview of next session-start injection
curl "http://127.0.0.1:37777/api/context/inject?project=labscript-suite" | wc -c
# expect: < 5000 bytes after Track B

# MCP enabled
curl http://127.0.0.1:37777/api/mcp/status
# expect: {"enabled":true}

# Chroma healthy (or knowingly disabled)
curl "http://127.0.0.1:37777/api/chroma/status?deep=1"

# DB still growing
curl http://127.0.0.1:37777/api/stats
```

## Implementation Order

1. Snapshot:
   ```bash
   mkdir -p ~/.claude/plans/backups
   cp ~/.claude-mem/settings.json ~/.claude/plans/backups/claude-mem-settings-2026-05-24.json
   curl http://127.0.0.1:37777/api/settings > ~/.claude/plans/backups/claude-mem-runtime-2026-05-24.json
   ```
2. **A1**: enable MCP via curl POST, verify
3. **A2**: edit settings.json with `CHROMA_MODE=persistent`, `npx claude-mem restart`, check `chroma/status?deep=1`; fall back to `CHROMA_ENABLED=false` if unhealthy
4. **A3 + B1 + B2**: write the combined settings.json block
5. **Restart Claude Code** (full session — verify against docs whether worker restart suffices)
6. **Verify** via the four curl checks above
7. **Observe 2-3 working sessions**, then audit:
   - smart-explore reachable? (`smart_search "post_experiment"`)
   - Folder CLAUDE.md content in new obs?
   - Did I cite injection content? If consistently no → drop OBSERVATIONS/SESSION_COUNT/FULL_COUNT to 0 (rev 3 Phase 2 escalation)
8. Schedule Track C follow-up plans (C1 pathfinder, C2 corpora, C3 make-plan adoption)

## Rollback Procedure

| Step | Rollback |
|---|---|
| A1 (MCP) | `POST /api/mcp/toggle {"enabled":false}` |
| A2 chroma persistent | Set `CHROMA_MODE=local` or `CHROMA_ENABLED=false` |
| A3 (folder CLAUDE.md) | `FOLDER_CLAUDEMD_ENABLED=false` |
| B1 (injection) | Restore settings.json snapshot |
| B2 (skip tools) | Restore original `SKIP_TOOLS` value |
| Full rollback | `cp ~/.claude/plans/backups/claude-mem-settings-2026-05-24.json ~/.claude-mem/settings.json`, POST mcp toggle false, `npx claude-mem restart` |

DB and observations never modified — no data loss.

## CLI Safety Addendum (NEW)

**The install trap is real.** Per CLI agent: bare `npx claude-mem` or any unknown flag → defaults to `install`. `--help` is whitelisted at top level only; `install --help` runs the installer.

**Never run in non-TTY**: install, repair, update, uninstall, start, stop, restart, adopt, cleanup, transcript watch, all `server start/stop/api-key/jobs` variants.

**Safe read-only**: `version`, `--version`, `-v`, `help`, `--help`, `-h`, `status`, `worker status`, `server status`, `search <query>`, the 5 `server logs|doctor|migrate|export|import` stubs.

**For diagnostics, prefer the REST API** at `:37777` (especially `/api/admin/doctor`) — bypasses the unreliable `status` PID-file probe.

Add corresponding rule to native MEMORY.md.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| A2 persistent mode unsupported on Windows | Fall back to `CHROMA_ENABLED=false`; lose `/api/search/by-*` (keep `/api/search/observations`, `/api/context/recent`, `/api/observations/by-file`) |
| B2 SKIP_TOOLS too aggressive, lose useful recall | Remove specific tools (e.g. keep WebFetch out of skip list) |
| Folder CLAUDE.md injection bloats observations | Set `FOLDER_CLAUDEMD_ENABLED=false`; existing obs untouched |
| Settings change requires Claude Code restart | Test at impl Step 5 |
| Plugin upgrade overwrites settings | `~/.claude-mem/settings.json` is user data, persistent |
| Accidental install via CLI flag | CLI Safety Addendum + rule in native MEMORY.md |
| Per-prompt injection still surfaces unwanted content | Drop counts to 0 (Phase 2 escalation from rev 3) |

## Alternatives Considered

- **Phase 3 / full disable** (rev 2): rejected per hard constraints — `smart-explore` requires worker + MCP
- **Custom mode authoring (`~/.claude-mem/modes/`)**: rejected — modes agent confirmed user dir is NOT searched
- **`CLAUDE_MEM_MODE=code--chill` activation**: rejected — chill skips "exploratory code reading" where our best gotchas come from
- **Install chroma standalone server** (Track A2 Option β): deferred unless persistent mode fails
- **`transcripts watcher` config**: skipped — Claude Code feeds transcripts via hooks already
- **`server-beta` cloud sync**: skipped — single-machine
- **`telegram` notifications**: skipped — no bot, no use case
- **mem0 / Letta / Zep migration**: rejected — disruption exceeds value

## Sources / Evidence

Local data:
- DB: `~/.claude-mem/claude-mem.db` — 928 obs, ~152 summaries
- Plugin source: `~/.claude/plugins/cache/thedotmack/claude-mem/13.3.0/` (newest, active)
- Live runtime: `curl http://127.0.0.1:37777/api/settings`
- Live chroma: `curl http://127.0.0.1:37777/api/chroma/status?deep=1`
- Live MCP: `curl http://127.0.0.1:37777/api/mcp/status`

Reference docs from this session's 6-agent investigation:
- [notes/2026-05-24_claude-mem-env-vars-reference.md](../../../../notes/2026-05-24_claude-mem-env-vars-reference.md) — exhaustive env var table (71 keys)
- `~/.claude/projects/c--Users-radmo-labscript-suite/memory/reference_claude-mem-cli-surface.md` — CLI safety map

Official docs:
- https://docs.claude-mem.ai/file-read-gate.md
- https://docs.claude-mem.ai/architecture/hooks.md
- https://docs.claude-mem.ai/architecture/worker-service.md
- https://docs.claude-mem.ai/architecture/search-architecture.md
- https://docs.claude-mem.ai/configuration.md
- https://docs.claude-mem.ai/modes.md

Community:
- https://docs.bswen.com/blog/2026-03-26-claude-code-memory-built-in-vs-claude-mem/
- https://ddewhurst.com/blog/claude-mem-vs-auto-memory/

Session incidents:
- `npx claude-mem install --help` ran the installer (CLI Safety Addendum captures the rule)
- `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` re-added on install; manually removed
- v13.3.0 installed alongside v13.2.0 (intentional cache, hooks resolve newest)
