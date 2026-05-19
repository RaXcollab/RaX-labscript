---
name: agent-workflow
description: Agent orchestration rules for multi-step tasks — file-to-agent routing, session-notes, wrap-up, plan mode integration, and deliverables checklist. Auto-loads when planning multi-agent work.
user-invokable: false
---

# Agent Orchestration

Invoke agents proactively based on task type. Don't wait for the user to ask.

## Dispatch Table

| Task type | Agents to invoke | When |
|---|---|---|
| New device integration | `device-builder` (planning + implementation) | During plan/design/build |
| BLACS crash / thread issue | `blacs-expert` → `labscript-diagnostics` | Immediately |
| Experiment sequence design | `amo-expert` | When writing sequences or connection tables |
| Analysis work | `lyse-analysis` | When touching analysislib/ |
| Codebase audit / code review | Domain agents per routing table below | Never use generic Explore for audits — it produces false positives on physics-lab conventions |

## File-to-Agent Routing

Route findings through the domain agent that owns each path. Generic Explore agents lack physics-lab context.

| Path pattern | Route to | Why |
|---|---|---|
| `labscriptlib/` (sequences, connection tables, globals) | `amo-expert` | RunManager globals, device config semantics |
| `analysislib/` (analysis scripts, notebooks) | `lyse-analysis` | API stability, utility library conventions |
| `user_devices/` (BLACS device classes) | `device-builder` (confers with `blacs-expert` + `amo-expert`) | Thread safety, state machine, ZMQ protocol |
| `blacs/` (BLACS runtime, base classes) | `blacs-expert` | State machine, Qt threading, base class behavior |
| `labscript-devices/` (official device drivers) | `blacs-expert` | Device driver internals, NI_DAQmx patterns |
| `labscript-utils/` (shared utilities) | `blacs-expert` | Utility internals, h5_lock, properties |
| `logs/` (BLACS.log, faulthandler) | `labscript-diagnostics` | Log parsing, recurrence analysis |
| `notes/` (lab notes, session history) | `labscript-diagnostics` | Correlate errors with recent changes |
| External GUI codebases | Local agent in `.claude/agents/` of the GUI directory | GUI internals, motor control, ZMQ server |

**External GUI agent discovery:** Check for `.claude/agents/` inside the GUI's codebase directory (e.g., `GUIs/rastering/.claude/agents/ablation-tech.md`). The External GUI Registry in CLAUDE.md lists each GUI's codebase path.

## Routing Enforcement

Before launching any Explore or Plan agent, check the routing table. If the task touches files owned by a domain agent, use that domain agent instead. This applies to plan mode Phase 1 (exploration) and Phase 2 (design). The routing table is authoritative; generic agents are a last resort for truly cross-cutting or novel tasks.

## Plan Mode Integration

- Use specialized agents (`device-builder`, `blacs-expert`, `amo-expert`) as your Explore/Plan agents for domain-matching tasks
- Don't default to generic Explore/Plan when a specialized agent exists
- **Small fixes** (single-file, ~10 lines, obvious approach): Don't use full multi-phase plan mode. State the fix in a few sentences, ask for permission, one cycle.
- **Full plan mode**: Multi-file changes, architectural decisions, unclear requirements, or anything the user explicitly requests planning for.

### Agent Dispatch Declaration (required for full plan mode)

At the START of Phase 1, before launching any agents, state an **Agent Dispatch Table** listing which agents will be used and why:

```
| Agent | Purpose | Phase |
|-------|---------|-------|
| blacs-expert | Audit worker lifecycle, thread safety | Phase 1 + 2 |
| amo-expert | Verify sequence-side patterns, DO table | Phase 1 + 2 |
```

This prevents: (a) forgetting to launch experts, (b) using generic Explore for domain tasks, (c) missing cross-device impact analysis.

### Cross-Audit Rule

For **BLACS worker changes** (safety-critical — affects live hardware): every claim audited by one expert must be cross-audited by the other. State cross-audit status in the plan's Agent Audit Trail table. Do not exit plan mode with unaudited claims.

## Parallel Dispatch & Forking

Multi-agent env is enabled (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, `CLAUDE_CODE_FORK_SUBAGENT=1`). Use it:

- **Independent path-routed audits → dispatch in ONE message.** When several routing-table paths are touched (e.g. `user_devices/` + `analysislib/` + `logs/`), launch their domain agents concurrently in a single response, not serially.
- **Cross-Audit Rule → fork, don't re-explain.** For the BLACS cross-audit, fork `blacs-expert` and `amo-expert` from the shared plan context so both see *identical* claims (fork inherits full parent context + ~90% prompt-cache savings on children 2..N). Follow with one synthesis pass that reconciles their findings.
- **Use fresh (non-fork) subagents for adversarial work.** Code review, security review, and "find what's wrong" audits must NOT be forks — a fork inherits the parent's assumptions and will gloss over the same bugs. Spawn a clean `subagent_type` instead.
- **Orchestrator stays orchestrator.** During any multi-agent run, the lead routes and synthesizes — it does not also do domain work in parallel.
- **Team size 2–3.** Coordination overhead exceeds parallelism gains past ~3 concurrent teammates.
- **Plan-mode cost caveat.** Agent *teams* cost ≈7× tokens in plan mode (each teammate re-runs planning). While planning, prefer parallel one-shot subagents or forks over teams.
- **Known bug:** never combine `isolation: "worktree"` with `team_name` — agents silently land in the main repo. Use separate Agent calls or verify isolation explicitly.

## Session Notes Protocol

- At session start, ask the user if they want session-notes tracking (use AskUserQuestion, short yes/no)
- If yes, launch `session-notes` agent in background and resume at milestones
- `session-notes` handles note-taking only — wrap-up deliverables are owned by `wrap-up`
- For pure config/tooling sessions (editing CLAUDE.md, agent prompts, settings, skills), session-notes can be skipped — the diffs serve as the record

## Agent Workflow (plan agent use upfront, not as afterthoughts)

1. **Plan phase:** Identify which domain agents to consult (routing table above), include `session-notes` for tracking, and include `wrap-up` for deliverables — all in the plan itself.
2. **Implementation phase:** Execute with domain agents. `session-notes` runs in background.
3. **Deliverables phase:** `wrap-up` agent runs its fixed pipeline.

The Deliverables section of every plan must specify which agents produce which artifacts, so nothing is forgotten.

## Standard Deliverables Checklist (owned by `wrap-up` agent)

1. Commit(s) — to correct repo(s)
2. HTML lab note — `notes/YYYY-MM-DD_Topic.html`
3. Session introspection — what went well, what to improve, lessons
4. CLAUDE.md / agent prompt updates — if conventions changed

