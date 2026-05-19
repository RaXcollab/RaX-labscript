# Claude Code for RaX Labscript

This guide explains how to use [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — Anthropic's AI coding assistant — with the RaX labscript suite. The setup is pre-configured with custom agents that understand our codebase, hardware, and conventions.

## Quick Start

1. Open a terminal in the `labscript-suite/` directory.
2. Run:
   ```
   claude
   ```
3. Ask your question in plain English. Claude has access to all files in the repo and knows the project structure.

## What Claude Already Knows

On every session start, Claude reads [`CLAUDE.md`](CLAUDE.md) in the repo root. This file contains:

- The multi-repo structure (labscript-suite, blacs, labscript-devices, labscript-utils)
- Which repo is user-facing vs backend
- Key conventions (e.g., `inmain()` for Qt thread safety, worker path format)
- The ExternalSoftware / RemoteControl communication pattern
- Log file locations and conda environment setup

You do not need to re-explain any of this each session.

## Custom Agents

Eight specialized agents Claude auto-invokes by task type (request any by name too). Full prompts in `.claude/agents/`; orchestration rules in `.claude/skills/agent-workflow/`.

| Agent | Use it for |
|---|---|
| `amo-expert` | Experiment sequences, connection tables, runmanager scans, NI hardware, physics-side scripting |
| `blacs-expert` | BLACS runtime internals, Qt thread safety, state machine, device lifecycle, NI_DAQmx worker |
| `device-builder` | Scaffolding new BLACS device classes (5-file RemoteControl pattern) + external GUI integration |
| `lyse-analysis` | Analysis scripts and Jupyter notebooks, lyse utility API |
| `labscript-diagnostics` | BLACS/labscript log triage, crash/error diagnosis, recurrence analysis (sonnet) |
| `session-notes` | Lightweight background session note-taking (sonnet) |
| `wrap-up` | End-of-session deliverables: commits, HTML lab notes, introspection, context updates |
| `context-auditor` | Audits context health vs best practices; researches new practices (multi-source) |

External GUI codebases under `GUIs/` each carry their own `.claude/agents/`: `GUIs/rastering` → `ablation-tech`, `GUIs/BigSkyControl` → `bigsky-yag-laser-controller`, `GUIs/HF_Locking` → `pid-persistence`. Use the GUI-local agent for that GUI's internals; use `amo-expert`/`blacs-expert` for BLACS-side architecture.

Example prompts:
- "Create a new RemoteControl device for the rastering GUI" → `device-builder`
- "BLACS crashed, what happened?" → `labscript-diagnostics`
- "Write an absorption-imaging sequence" → `amo-expert`
- "Wrap up this session" → `wrap-up`

## Tips

- **Be specific.** "The laser lock tab throws a timeout during transition_to_buffered" is better than "the laser lock doesn't work."
- **Reference files.** "Look at `blacs_tabs.py` in RemoteControl" helps Claude focus.
- **Ask for explanations.** "Explain how `check_remote_values` works in the base class" is a great way to learn the codebase.
- **Use for debugging.** Paste an error traceback and ask "what caused this?" — Claude will trace it through the codebase.
- **Creating new devices.** When building a new ExternalSoftware integration, ask Claude to use the RemoteControl template as a starting point.

## Configuration Files

All Claude Code configuration lives in the `.claude/` directory (tracked in git):

| File | Purpose |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Project instructions loaded every session |
| `.claude/agents/amo-expert.md` | AMO/Labscript code agent prompt |
| `.claude/agents/labscript-diagnostics.md` | Log analysis agent prompt |
| `.claude/settings.local.json` | Local permission settings |

To update what Claude knows about the project, edit `CLAUDE.md`. To change agent behavior, edit the files in `.claude/agents/`.

## Reference Documentation

- [`Labscript-Confluence-2026-02-11.pdf`](Labscript-Confluence-2026-02-11.pdf) — Lab Confluence docs covering installation, connection tables, ExternalSoftware communication pattern, and debugging notes. Claude can read this PDF when needed.
