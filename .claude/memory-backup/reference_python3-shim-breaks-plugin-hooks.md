---
name: python3-shim-breaks-plugin-hooks
description: "Plugin hooks that hardcode `python3` are silently dead on this PC; fix is a python3.exe copy in miniconda root"
metadata: 
  node_type: memory
  type: project
  originSessionId: cd6eb426-83fe-4009-b169-14e7b5f66efe
---

Any Claude Code plugin whose `hooks.json` invokes `python3` (e.g. hookify: PreToolUse/PostToolUse/Stop/UserPromptSubmit all run `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/*.py`) was **silently non-functional** on this machine. Bare `python3` resolved only to the Microsoft Store App Execution Alias shim (`C:\Users\radmo\AppData\Local\Microsoft\WindowsApps\python3.exe`), which prints "Python was not found" and exits non-zero. Hook failures are silent — no surfaced error.

**Fix applied (2026-05-15):** copied `C:\Users\radmo\miniconda\python.exe` → `C:\Users\radmo\miniconda\python3.exe`. miniconda is prepended to the live process PATH (conda activation) ahead of WindowsApps, so both Git Bash and cmd.exe resolve `python3` → real Python 3.13.11, and hook subprocesses inherit this. Verified end-to-end: hookify `pretooluse.py` fed a Bash event returns `{}` exit 0. Reversible: `rm C:\Users\radmo\miniconda\python3.exe`.

**Why:** the registry User PATH lists WindowsApps first and has no miniconda; only the live conda-activated process PATH puts miniconda first. **How to apply:** if Claude Code is ever launched without conda activation, `python3` reverts to the broken shim — keep this in mind when diagnosing dead plugin hooks. The hand-written guard in `.claude/settings.json` is unaffected (it uses `python`, not `python3`).

Secondary latent hookify bug: `load_rules()` globs `.claude/hookify.*.local.md` relative to CWD — rules only load when CWD = project root. No hookify rule files currently exist (user chose "no rules for now"). hookify-plus (`github.com/adrozdenko/hookify-plus`) is a community fork adding `not_regex_match`/`value`/`read`; not in the official marketplace; would inherit the same `python3` issue. See [[device-internals]].
