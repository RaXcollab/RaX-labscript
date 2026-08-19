# Handoff: Install documentation + repo portability

**Status: work LANDED on branch `docs/install-and-portability` (3 commits), NOT pushed, NOT merged. `master` untouched at `1776273`. The whole session ran on a collaborator's dev machine, NOT the lab control PC — nothing here has been exercised against a live labscript install.**

Session goal, in the operator's words: *"the entire goal of this session is repo portability for the labscript fork ... our collaborators will want to fork our modified labscript code."*

## Machine context (read this first)

This ran on `FRIB-HARVARD`, user `EBADI` — **not** `RaX-Control` / `radmo`. Consequences:

- There is **no `labscript` conda env here**. Only `base`, `lakeshore`, `sims` exist, under a system-wide Anaconda at `C:\ProgramData\anaconda3`. There is no `~/miniconda`.
- Nothing was verified by importing labscript, launching BLACS, or running a shot. Every claim below is from reading source, running git, or running the new scripts — never from a live suite.
- **Anything in this handoff that asserts runtime behaviour of the suite should be re-verified on `RaX-Control` before being trusted.**

## Where the checkout now lives

`C:\Users\EBADI\labscript-suite` — moved there this session so it satisfies the hardcoded profile path.

`labscript_profile/__init__.py:25` sets `LABSCRIPT_SUITE_PROFILE = Path("~" + getuser()).expanduser() / 'labscript-suite'`. Hardcoded, no env-var override. A checkout anywhere else does not error — labscript silently creates an *empty* profile at the correct path and uses that, so `userlib` imports fail with no obvious cause.

**The move went wrong partway and was repaired.** Two `Move-Item` attempts were blocked (VS Code held a handle, then this Claude session's own watcher on `.claude/skills`), and one of them **partially executed** — it moved files rather than copying, leaving the tree split across two locations with a `.git` in each. Repaired by verifying the two halves were disjoint, then moving the remainder directory-by-directory. Post-repair verification: `git fsck` clean, working tree clean, 254 `userlib` files present (matching the pre-move count), all six nested repos on correct branches and clean. The old path's empty shells were removed; `C:\Users\EBADI\labscript` is now an empty directory.

Watch item: if anything looks missing under `userlib/`, this partial move is the first suspect.

## Landed commits (branch `docs/install-and-portability`, no upstream set)

| Commit | Contents |
|---|---|
| `af2f56a` | `INSTALL.md`, `repos.yml`, `bootstrap.ps1` |
| `3ea6167` | `environment.yml`, conda auto-detection across 4 scripts, `_conda-path.ps1`, bootstrap stderr fix |
| `d27d323` | Stale pyzmq version in the INSTALL.md verification checklist |

Push when ready: `git push -u origin docs/install-and-portability`.

## New files

- **`INSTALL.md`** — consolidated install guide. Branches at §0 on whether labscript is already installed; §3 installs stock labscript, §5–§6 layer the fork on top. Leads with the directory layout because that is the easiest thing to get wrong.
- **`repos.yml`** — pins the three backend forks by commit: `blacs 81316aa`, `labscript-devices b32c97e`, `labscript-utils 25cee8c`. This closes the reproducibility gap — nothing previously recorded which backend commits belong with a given parent commit, so a fresh clone picked up each fork's default branch as of that day.
- **`bootstrap.ps1`** — clones/updates the backends to the pinned commits. `-Latest` for branch tips (the normal dev state), `-Install` for the editable install, `-UpdatePins` to re-record HEADs after validating a new set. All four modes were run successfully against the real repos.
- **`environment.yml`** — canonical conda spec (see next section).
- **`.claude/hooks/_conda-path.ps1`** — `Get-CondaBase` / `Get-CondaEnvPython`, used by the syntax hook.

## OPEN DECISION: the pyzmq pin

`CLAUDE.md` pins `pyzmq=23.2.0` and says "do NOT upgrade". The `labscript` env was **measured at 25.1.0** on 2026-07-01 (`.claude/session-handoff-2026-07-01-claude-setup.md` §7–§8), and that handoff already flags the mismatch as unresolved (its §189 open item).

What is actually established is the **26.x ceiling** — 26.x breaks the inter-application sockets and kicks BLACS off its port. `environment.yml` therefore carries 25.1.0, because that is what demonstrably runs, and documents the disagreement rather than silently picking a side.

**Someone on `RaX-Control` should settle this**: run `conda list pyzmq` in the `labscript` env, and either correct `CLAUDE.md` or correct the environment. Do not "fix" `environment.yml` to 23.2.0 without testing.

## Where the environment is actually recorded

The Confluence guide cites a `conda_list_output.txt` attachment as the authoritative package list. **That attachment is not in the PDF export and not in this repo** — confirmed by search. The only in-tree record is `.claude/session-handoff-2026-07-01-claude-setup.md` §7–§8, which is what `environment.yml` was built from.

It disagrees with the `old_*environment.yml` files in several places: python **3.11.14** (not 3.11.9), labscript **3.4.0** (not 3.3.1), pyzmq as above. Also: **the `nidaqmx` pip package is deliberately absent** — NI access goes through PyDAQmx and the labscript-devices `NI_DAQmx` driver.

Refresh procedure, to run on the lab PC: `conda env export --from-history > environment.yml`.

## Portability fixes landed

Four scripts hardcoded one machine's conda path and silently did nothing elsewhere. All now resolve conda at run time via `$CONDA_EXE` → `conda` on `PATH` → common install locations:

| File | Was |
|---|---|
| `Launch Labscript.bat` | `%USERPROFILE%\miniconda\shell\condabin\conda-hook.ps1` (×3) |
| `.githooks/pre-push` | `$HOME/miniconda/etc/profile.d/conda.sh` |
| `.claude/hooks/check-py-syntax.ps1` | `C:\Users\radmo\miniconda\envs\labscript\python.exe` |
| `.claude/backup-memory.sh` | `~/.claude/projects/c--Users-radmo-labscript-suite/memory` |

Verified on this Anaconda-only machine — the exact case that was previously broken. The launcher reports and stops when detection fails; the hooks fail open. `backup-memory.sh` now derives the Claude Code project slug from the checkout path (`C:/Users/…` → `C--Users-…`).

## Corrections to claims made earlier in the session

Recorded because the operator pushed back on several and was right; do not let these regress into the docs.

- **`labscript-profile-create` colliding with the repo's `userlib` is a non-problem in the documented order.** It writes to `%USERPROFILE%\labscript-suite` regardless of cwd and raises `FileExistsError` (`create.py:28`, `:66`) only if `userlib/`, `labconfig/`, or `app_saved_configs/` already exist there. The Confluence order — env, then profile, then pull the repo — never collides. Only a clone-first order does.
- **Build tooling for `--no-build-isolation` is a non-issue.** `setuptools_scm` is a *runtime* dependency of labscript-utils (`labscript-utils/setup.cfg:38`), so the `labscript-suite` install already provides it, and conda ships `setuptools`/`wheel` with `pip`. Demoted to a troubleshooting note.
- **The `setuptools_scm` hazard is only about tags.** `labscript_utils/__version__.py:16` calls `get_version()` at import time when `.git` is present, so a non-`v*` tag reachable from HEAD on a backend breaks every import. Corollaries: no shallow clones, keep `git` on `PATH`. It does not affect normal operation. Already a lab-wide invariant in `CLAUDE.md`; the 2026-06-10 incident is in `docs/stable-snapshot-2026-06-09.md`.
- **Miniconda vs Anaconda does not matter to labscript.** Only the four scripts above cared, and they no longer do.
- **`.gitmodules` is inert.** Added in the repo's first commit `3bc4055`; gitlinks were never registered (`git log --all --diff-filter=A -- blacs labscript-devices labscript-utils` is empty). Deleting it is safe but was left alone as out of scope.

## Scope boundary (operator-stated)

**The GUIs are not part of the labscript repos and not part of this setup.** The suite is the parent plus `blacs`, `labscript-devices`, `labscript-utils` — matching the `CLAUDE.md` Repository Structure table, which lists exactly those and keeps the GUIs in the separate External GUI Registry.

`HF_Locking`, `rastering`, and `BigSkyControl` live under `GUIs/` by filing convention only. They run in their own conda envs and **each documents its own environment, dependencies, and launch command internally**. `repos.yml`, `bootstrap.ps1`, and `INSTALL.md` all exclude them deliberately — do not fold them back in.

## Not done / next actions

1. **Push the branch** and decide on merging to `master`.
2. **Settle the pyzmq pin** on `RaX-Control` (above).
3. **Validate the whole install path on a real machine.** `INSTALL.md` has never been followed end-to-end by anyone; it was assembled from sources, not from a performed install. The highest-value next step is a collaborator running it from scratch and recording where it breaks.
4. **Install the pre-push hook** on any working checkout: `cp .githooks/pre-push .git/hooks/pre-push && chmod +x .git/hooks/pre-push`. Not installed in this checkout.
5. **`.claude/settings.json`** still carries ~20 `radmo` absolute paths in its permission allow-list. Machine-specific by nature and not runtime code, so left alone — a collaborator just gets extra permission prompts. Templating them was offered and not taken up.
6. **`userlib/user_devices/__init__ .py`** (literal space) — already analysed in `docs/known-latent-issues.md:147` and cleared for deletion by `docs/ponytail-audit-2026-08-14-behavior-review.md:107` (inert; `user_devices` stays a namespace package either way). Belongs to the ponytail-audit workstream, not this branch.
7. **`old_environment.yml` / `old_fresh_environment.yml`** are superseded by `environment.yml` but kept — `old_environment.yml` is the only frozen export with exact build strings.

## Repo state at handoff

| Repo | Branch | HEAD | Dirty |
|---|---|---|---|
| parent | `docs/install-and-portability` | `d27d323` | clean |
| parent `master` | — | `1776273` | — |
| `blacs` | `master` | `81316aa` | clean |
| `labscript-devices` | `master` | `b32c97e` | clean |
| `labscript-utils` | `master` | `25cee8c` | clean |
| `GUIs/HF_Locking` | `main` | `bf25b37` | clean |
| `GUIs/rastering` | `main` | `bbf76d4` | clean |
| `GUIs/BigSkyControl` | `main` | `98ff562` | clean |
