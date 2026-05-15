# Session Handoff: Claude Code Setup Redesign
**Date**: 2026-04-02
**Status**: Brainstorming Phase 3 (clarifying questions complete, approaching design proposal)
**Resume with**: Read this file first, then ask user for the GitHub repos/articles they mentioned

---

## Mission

Redesign the Claude Code agent/skill/hook architecture for the RaX-Control experiment control PC. We have:
1. An 11-part recommendations document from another Claude session (on Arian's personal Mac) that did deep research on 62 installed skills, MCP servers, plugins, and structural patterns
2. Ground-truth evidence from 30 lab notes spanning 6 weeks of actual usage on THIS machine
3. The user's direct feedback on pain points

The goal is to synthesize these into a concrete, evidence-based redesign — not blindly follow the other session's recommendations.

---

## Context: Who and What

**User**: Shungo Fukaya (radmo) + Arian Jadbabaie — MIT EMA Lab, Garcia Ruiz group. Physics PhD researchers on the RaX molecular spectroscopy experiment (radium-based molecules).

**Machine**: RaX-Control (Windows 11 Pro for Workstations). Experiment control PC running labscript-suite stack:
- RunManager → compiles sequences to h5
- BLACS → executes: programs NI DAQ, PrawnBlaster timing, ZMQ GUIs  
- Lyse → real-time analysis per shot

**Hardware**: PrawnBlaster (COM4, master clock), NI PXIe-6361 (4 AI, 2 AO), NI PXIe-6535 (digital), NI PXI-5922 (scope), 3 ZMQ remote GUIs (BigSkyControl YAG lasers, HF_Locking wavemeter PID, rastering Thorlabs motors), plus 7 other standalone GUIs.

**Python**: 3.11.14 via Miniconda, 6 conda envs. Every Python command needs `source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript`.

---

## Input Document: Other Session's Recommendations

File: `C:\Users\radmo\Desktop\rax-control-skills-and-setup-recommendations.md` (very large, ~20K+ tokens)

### Part 1: 10 Structural Patterns (from analyzing 62 installed skills)
1. **Iron Law Guard Rails** — mandatory pre-action gates ("BEFORE attempting ANY fix, enumerate state transitions")
2. **Two-Stage Review** — dispatch separate reviewer subagents to check work from different angles
3. **Phased Reference Loading** — load docs only when needed for current phase, not all upfront
4. **Subagent Delegation for Heavy Context** — delegate large data reads (logs, h5 files) to subagents
5. **8-Step Sequential Checklist** — numbered sequence, no skipping
6. **Dual Workflow (CREATE/RESUME)** — skills with two entry points for fresh vs continued work
7. **Validation Before Finalization** — automated checks before declaring completion
8. **Error Escalation Ladder** — progressive escalation when fixes don't work (≥3 fails → question architecture)
9. **Mandatory Reference Loading** — skill refuses to proceed without loading specific reference material
10. **Silent Detection Before Asking** — check what's available before asking user questions

### Part 2: MCP Server Recommendations
- **context7** — library docs (numpy, scipy, h5py, PyQt5, etc.)
- **KeepGoing** — session-to-session checkpoint persistence
- **mcp-debugger** — step-through Python debugging (WE PUSHED BACK: impractical for live BLACS)
- **GitHub MCP** — PR/issue management across 4 repos
- **claude-code-4-science** — HDF5 tools, scientific expert personas
- **Custom MCP servers** (Phase 5/pioneer): labscript MCP, ZMQ status MCP, h5-shot MCP

### Part 3: 5 Custom Skill Templates
- `/hardware-debug` — systematic debugging with silent detection + iron law + escalation
- `/pre-experiment-check` — 8-step validation before running experiments  
- `/impact-check` — trace cross-file dependencies after edits
- `/run-analysis` — quick lyse analysis on h5 shots
- `/device-change` — safe multi-file device modification with two-stage review

### Part 4: Agent Architecture (11 → 4 agents)
**WE REJECTED THIS.** See "Pushbacks" section below.

### Part 5-9: Infrastructure fixes, memory strategy, plugins, safety, skills budget

### Part 10: Phased implementation (5 phases from "first session" to "quarter 1")

---

## Our Pushbacks Against the Other Session

These are things we verified against actual code and lab notes:

| Claim | Reality | Evidence |
|-------|---------|----------|
| "11 agents don't dispatch — too narrowly specialized" | GUI agents (BigSky, HF_Locking, rastering) live in `GUIs/{name}/.claude/agents/`, workspace-scoped. Don't compete with main 8. | Glob search of agent locations |
| "agent-workflow doesn't trigger consistently" | Has `user-invokable: false` — auto-loads. Dispatch table exists and routes by file path. | Read of SKILL.md frontmatter |
| "session-notes + wrap-up should be replaced by KeepGoing" | session-notes does domain categorization (DECISION, BUG, PATTERN) + pattern recognition. wrap-up runs fixed pipeline producing lab notes, commits, context updates. KeepGoing does checkpoints. Complementary. | Read of both agent definitions |
| "labscript-diagnostics overlaps blacs-expert" | Sonnet for log parsing, Opus for architecture reasoning. Intentionally different models for different cost/capability. | Frontmatter: `model: sonnet` vs `model: inherit` |
| "Collapse to 4 agents with 2K+ token prompts" | Static 2K prompt loads on EVERY task. Current setup loads narrow context per-task via path-scoped rules. More efficient with 1M context. | Token analysis |
| "Install mcp-debugger for step-through debugging" | Attaching debugger to live BLACS (PyQt5 + multiple threads + NI hardware) is impractical. | Domain knowledge |
| "Build custom labscript MCP server" | Significant project, not a quick win. Phase 5 timeline is appropriate. | Scope assessment |

---

## Evidence from 30 Lab Notes (Feb 21 — Mar 9, 2026)

### Agent Dispatch: The Actual Data

| Period | Sessions | Agent Proactively Used | Should Have Been |
|--------|----------|----------------------|------------------|
| Feb 21 (8 notes) | BigSkyHub integration, tab redesign, connection table sync, analysis cleanup, etc. | 0 proactive | 4+ |
| Feb 22-23 (4 notes) | Pre-scan audit, orchestration upgrade, LaserLock/Rastering tab redesign, codebase audit | Generic Explore used → 5/7 false positives | Domain agents needed |
| Feb 24-27 (5 notes) | Serial disconnect, safety rules, best practices rewrite, latched DO, ZMQ race | 0 | 3 |
| Mar 2-9 (7 notes) | Keep Warm, Q-switch fix, KeepWarm refactor, rastering audit, serial disconnect, stale cache | blacs-expert in 2 sessions | All 7 |

**Key finding**: Agent-workflow skill exists with auto-load, but Claude still doesn't dispatch ~80% of the time. Root cause: Claude decides it can handle the task by reading 2-3 files, which is often correct for the immediate fix but wrong about catching cross-file impact and state transitions.

### Bugs Agents Would Have Caught

1. **Q-switch mode qsm2 vs qsm0** (Mar 5) — blacs-expert reading yag-laser-physics.md would have known internal Q-switch is mode 0, not mode 2
2. **Optimistic cache before serial confirmation** (Mar 9) — 14 methods had the same bug. Pattern audit by an agent would have caught it in method 1, not after 14 were wrong
3. **Shutter scoping incident** (Feb 27) — amo-expert with labscript-api.md loaded would have known the Shutter constructor takes a delay TUPLE, not separate kwargs. Also would have known NI_DAQmx port atomicity (all 8 bits written together)
4. **Generic audit false positives** (Feb 23) — RunManager globals flagged as "undefined variables", num_lasers=1 flagged as "bug", __pycache__ flagged for cleanup. Domain agents would have filtered these.

### What Works Well (Evidence-Based — DON'T BREAK)

1. **Reference docs** (5 in `docs/`) — yag-laser-physics.md was created BECAUSE an agent got Q-switch wrong. Directly prevented repeat bugs.
2. **Path-scoped rules** (8 in `.claude/rules/`) — narrow, auto-load on file path match, low token cost. The devices.md rule auto-loads for user_devices/ edits.
3. **Two-phase audit** (explore → implement with manual verification) — Feb 23 codebase audit used this successfully
4. **Memory system** — 30+ actionable lessons (cache-after-confirm, lock scope, serial gateway, etc.) carry forward across sessions
5. **GUI-specific agents** in workspace-scoped directories — don't compete with main routing
6. **Delta tracking + cooldown guards** — standard workarounds for BLACS base class friction, well-documented
7. **Signpost pattern** — BLACS_COMMUNICATION_CONTRACT.md lets GUI agents work independently

### Recurring Bug Patterns (What the System Should Prevent)

| Pattern | Count | Sessions |
|---------|-------|----------|
| Stale cached state diverging from hardware | 3 | Mar 2 (temp polling), Mar 6 (serial disconnect), Mar 9 (cache-before-serial) |
| Serial disconnect/reconnect state management | 3 | Feb 24, Mar 6, Mar 9 |
| Lock scope too narrow for concurrent code | 2 | Mar 2 (temp polling timer), Mar 6 (raster enqueue race) |
| ZMQ timeout/blocking | 2 | Mar 6 (DAQmx), Feb 27 (EFSM race) |
| Cross-file coordination required | 4 | Feb 24 (3 files), Feb 26 (10+ files), Mar 5 (dual-YAG), Mar 6 (rastering audit) |
| Agent guessing instead of reading reference | 2 | Feb 27 (shutter constructor), Mar 5 (Q-switch mode) |

---

## User's Pain Points (Direct Feedback)

**Top 3** (prioritized by user):
- **(a) Permissions whack-a-mole** — constantly hitting Allow for safe read/grep/git operations
- **(b) Agents not dispatching** when they should
- **(c) Claude not understanding labscript** internals

**Also important** (user confirmed all valid):
- (d) Cross-file breakage after edits
- (e) Broken fixes that miss state transitions
- (f) Cold starts every session (no memory of yesterday)
- (g) Generic agents producing false positives on physics code

---

## Agreed Design Decisions

### Agent Consolidation: 8 main → 3 agents + 3 new skills

| Current | Proposed | Type | Status | Rationale |
|---------|----------|------|--------|-----------|
| blacs-expert + labscript-diagnostics | **blacs-expert** | Agent | **AGREED** | Merge. Diagnostics is always step 1 of blacs-expert work. Sonnet cost saving (~$0.02/invocation) not worth routing confusion. Add "Phase 0: check logs first" to blacs-expert prompt. |
| amo-expert | **`/sequence-check`** (expand existing `/check-sequence`) | Skill | **AGREED** | Agent reasoning not needed — it just reads files. Failed on shutter incident because it didn't load ref docs. A skill with mandatory reference loading (labscript-api.md + connection table) fixes this. User noted: "amo-expert doesn't know enough about labscript or physics" to be useful as an agent. |
| lyse-analysis | **lyse-analysis** | Agent | **AGREED** | Keep. Clear domain, needs reasoning for h5 data analysis + optimization. |
| device-builder | **device-builder** | Agent | **AGREED** | Keep. Clear domain, scaffolding new 5-file device integrations. |
| context-auditor | *(delete)* | — | **AGREED** | Use `claude-md-management` plugin instead (already installed). Add memory-audit step to /wrap-up. |
| session-notes | **`/note`** | Skill | **AGREED** | Append timestamped entry to scratch file. Lab notes show background agent frequently not launched even when mandatory. Simpler, honest about when it fires. |
| wrap-up | **`/wrap-up`** | Skill | **AGREED** | Fixed pipeline: diffs → commits → lab note → **introspection/reflection/brainstorm improvements** → memory update → rules/docs update. User emphasized: "the important thing is learning, reflecting, and brainstorming ways to improve." |

**3 GUI-specific agents stay** in `GUIs/{name}/.claude/agents/` — workspace-scoped, not part of routing problem.

**Result**: 3 main agents (blacs-expert, lyse-analysis, device-builder) + 3 new skills (/note, /wrap-up, expanded /sequence-check)

### Three Core Problems to Solve

**(A) Agent dispatch** — agents exist but don't fire 80% of the time
- Root cause: Claude decides it can handle tasks by reading files directly
- Proposed fixes being considered:
  - Better agent descriptions that match more task phrasings
  - PostToolUse hook that reminds Claude to consider agents after reading device files
  - Path-based dispatch (file triggers agent) vs description-based (task matches agent)
  - SessionStart hook injecting agent registry

**(B) Cross-file impact** — Claude fixes one file, breaks another (4 of 30 sessions)
- Proposed: `/impact-check` skill + PostToolUse warning hook after device file edits
- The other session's proposal for this is solid

**(C) State transition coverage** — Claude misses reconnect, timeout, abort paths (3+ sessions)
- Proposed: Iron law in BOTH places:
  - `devices.md` rule (auto-loads when editing device files — catches the 80% case where agents don't fire)
  - Agent prompts (blacs-expert, device-builder — catches the 20% case where agents do fire)
- User agreed with **(c) both** approach

### Infrastructure Fixes (All Agreed)

1. **Permissions overhaul**: Add broad read-only patterns to settings.json
   - `Read(*)`, `Grep(*)`, `Glob(*)` — no reason to ever block reads
   - `Bash(git *)` — all git read operations
   - `Bash(ls *)`, `Bash(find *)`, `Bash(which *)` — safe utilities
   - `Bash(python -c *)`, `Bash(conda *)`, `Bash(pip list*)`, `Bash(pip show*)` — safe Python checks
   - `Bash(source ~/miniconda*)` — required for ALL Python commands

2. **Connection table protection hook**: PreToolUse BLOCK (exit 2) on Edit/Write to `connection_table.py`, `connection_table.h5`, `BaF_globals.h5`

3. **Cross-file impact warning hook**: PostToolUse WARN (exit 0) after editing `user_devices/` or `connection_table` files — reminds Claude to check adjacent layers

4. **WebFetch domains to add**: ni.com, knowledge.ni.com, thorlabs.com, numpy.org, docs.scipy.org, matplotlib.org, pyserial.readthedocs.io, pyvisa.readthedocs.io, docs.python.org, stackoverflow.com, arxiv.org

5. **MCP servers to install**:
   - context7 (library docs) — `claude mcp add context7 -- npx -y @upstash/context7-mcp@latest`
   - KeepGoing (session persistence) — `claude mcp add keepgoing -- npx -y @keepgoingdev/mcp-server`
   - context-mode (already installed this session)

---

## Open Items (Resume Here)

### Waiting on User
1. **GitHub repos/articles** — user said they have more context to share (repos, articles about Claude Code patterns). They want to use context-mode's `ctx_fetch_and_index` to read them without polluting context.

### Still Being Designed
2. **Exact iron law wording** for devices.md rule — need to balance thoroughness vs not being so long it gets ignored
3. **Agent-workflow skill fate** — keep, modify, or replace with SessionStart hook?
4. **Which of the 10 structural patterns** (other session Part 1) actually apply vs are over-engineered for our context
5. **Skill templates from Part 3** — which to build, in what order. /pre-experiment-check and /impact-check seem highest value. /hardware-debug overlaps with enhanced blacs-expert.
6. **Permission patterns** — exact glob syntax that works on Windows Git Bash

### Brainstorming Checklist Status
- [x] Phase 1: Explore project context (done — read all settings, agents, skills, rules, 30 lab notes)
- [ ] Phase 2: Visual companion offer (skip — no visual content needed)
- [x] Phase 3: Clarifying questions (in progress — main questions answered, waiting on articles)
- [ ] Phase 4: Propose 2-3 approaches
- [ ] Phase 5: Present design
- [ ] Phase 6: Write design doc
- [ ] Phase 7: Spec self-review
- [ ] Phase 8: User reviews spec
- [ ] Phase 9: Transition to writing-plans

---

## Files Modified This Session

- `C:\Users\radmo\Desktop\Claude-Code-Setup-Report.md` — NEW: Full environment audit
- `C:\Users\radmo\Desktop\RaX-Control-Context-Prompt.md` — NEW: Synthesized context for other sessions
- `C:\Users\radmo\.claude.json` — MODIFIED: Added context-mode MCP server config
- `C:\Users\radmo\labscript-suite\.claude\session-handoff-2026-04-02.md` — NEW: This file

## Key Files to Read on Resume

```
# Current architecture (what we're changing)
.claude/agents/*.md                    — 8 current agent definitions
.claude/skills/*/SKILL.md             — 5 current skill definitions
.claude/rules/devices.md              — where iron law would go
.claude/rules/analysis.md             — analysis-specific rules
.claude/settings.json                 — current 83 permission rules + hooks
~/.claude/settings.json               — user-level: model, plugins, WebFetch
CLAUDE.md                             — root context (129 lines)
docs/                                 — 5 reference docs + context-best-practices

# Evidence base
notes/*.html                          — 30 lab notes (read summaries above, not raw files)

# Other session's input
Desktop/rax-control-skills-and-setup-recommendations.md  — full 11-part document

# This handoff
.claude/session-handoff-2026-04-02.md — this file
```
