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

We have two specialized agents that Claude automatically uses when relevant. You can also request them explicitly.

### labscript-amo-expert

**When it activates:** Any question about Labscript code, device classes, BLACS tabs/workers, connection tables, runmanager, lyse, or experiment sequences.

**What it knows:**
- The 3-class device pattern (labscript_devices.py, blacs_tabs.py, blacs_workers.py)
- RemoteControl / ExternalSoftware template for integrating external GUIs
- BLACS state machine internals (event ordering, initialization sequence)
- Qt thread safety rules (critical for avoiding crashes)
- NI PXIe hardware conventions

**Example prompts:**
- "Help me create a new RemoteControl device for the rastering GUI"
- "Why is my device tab crashing when it tries to update a widget?"
- "How do I add a new analog monitor channel to the laser lock tab?"
- "Walk me through the shot lifecycle for our BaF sequence"

### labscript-diagnostics

**When it activates:** Any question about logs, crashes, errors, or system health.

**What it knows:**
- Log file locations (`logs/BLACS.log`, `logs/BLACS_faulthandler.log`)
- How to interpret faulthandler output (C-level crash traces vs Python tracebacks)
- Common error categories (device communication, Qt thread safety, queue manager, connection table)
- BLACS state machine event ordering (for diagnosing race conditions)

**Example prompts:**
- "BLACS crashed, what happened?"
- "Check the logs for any errors from the last few shots"
- "We're getting intermittent timeouts on the PrawnBlaster"
- "Increase logging verbosity for the connection table parser"

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
| `.claude/agents/labscript-amo-expert.md` | AMO/Labscript code agent prompt |
| `.claude/agents/labscript-diagnostics.md` | Log analysis agent prompt |
| `.claude/settings.local.json` | Local permission settings |

To update what Claude knows about the project, edit `CLAUDE.md`. To change agent behavior, edit the files in `.claude/agents/`.

## Reference Documentation

- [`Labscript-Confluence-2026-02-11.pdf`](Labscript-Confluence-2026-02-11.pdf) — Lab Confluence docs covering installation, connection tables, ExternalSoftware communication pattern, and debugging notes. Claude can read this PDF when needed.
