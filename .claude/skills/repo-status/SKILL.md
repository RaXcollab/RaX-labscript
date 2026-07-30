---
name: repo-status
description: Show branch, ahead/behind, dirty count, and worktree relationships for every repo in the labscript-suite workspace
---

One-shot status table across every git repo and linked worktree in the workspace: current branch, ahead/behind the last-fetched upstream, dirty entry count (porcelain lines — an untracked directory counts as one entry — excluding the always-dirty `calibration_data.json`), and which main repo a worktree belongs to.

## How repos are discovered

Walks the workspace up to depth 3, same exclusions as `revert-to-main` (`node_modules`, `__pycache__`, `.ipynb_checkpoints`, `worktrees`). Unlike `revert-to-main`, a `.git` **file** (linked worktree) counts as well as a `.git` directory. Non-repos like `GUIs/rastering-stepping`, `GUIs/envs`, and `GUIs/graphify-out` are excluded by that `.git`-existence test (they have none); each surviving candidate is additionally confirmed with `git -C <dir> rev-parse --show-toplevel` equal to `<dir>` itself — belt-and-braces against nested/submodule directories — and never by name pattern.

The 15 expected repos are hardcoded from the 2026-07-30 workspace scan (plan Phase 0 of `2026-07-30-claude-automation-upgrades`) — note this is broader than CLAUDE.md's External GUI Registry, which lists only the three BLACS-integrated GUIs. Any expected repo not found gets a `MISSING` row instead of being silently dropped — that's how a deleted worktree shows up. New repos are discovered automatically; add them to the hardcoded list to get MISSING protection.

## Read-only

No `git fetch` is ever run. Ahead/behind counts reflect whatever the last fetch (by any tool) left in the remote-tracking refs — the Report section says so explicitly.

## Procedure

```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python -c "
import subprocess, os
ROOT = r'C:/Users/radmo/labscript-suite'
EXCLUDED_DIRS = {'node_modules', '__pycache__', '.ipynb_checkpoints', 'worktrees'}
MAX_DEPTH = 3
EXPECTED = [
    '.', 'blacs', 'labscript-devices', 'labscript-utils',
    'GUIs/BigSkyControl', 'GUIs/HF_Locking', 'GUIs/HF_Locking-zmq-v2',
    'GUIs/LabMonitoring', 'GUIs/LakeshoreGUI', 'GUIs/Microcontrollers',
    'GUIs/MKS_Flowcontroller_v2', 'GUIs/quadmag_gui', 'GUIs/rastering',
    'GUIs/rastering-zmq-v2', 'GUIs/Thermocouples',
]

def git(cwd, *args):
    r = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def discover(root):
    repos = []
    root_norm = root.replace('\\\\', '/').rstrip('/')
    for dp, dns, _ in os.walk(root):
        norm = dp.replace('\\\\', '/').rstrip('/')
        depth = 0 if norm == root_norm else norm[len(root_norm):].count('/')
        dns[:] = [d for d in dns if d not in EXCLUDED_DIRS]
        if os.path.exists(os.path.join(dp, '.git')):
            rc, top, _ = git(dp, 'rev-parse', '--show-toplevel')
            if rc == 0 and os.path.normpath(top).lower() == os.path.normpath(norm).lower():
                rel = os.path.relpath(dp, root).replace('\\\\', '/')
                repos.append('.' if rel == '.' else rel)
        if depth >= MAX_DEPTH - 1:
            dns[:] = []
    return repos

discovered = set(discover(ROOT))
rows = []
for repo in sorted(set(EXPECTED) | discovered, key=lambda p: (p != '.', p)):
    cwd = f'{ROOT}/{repo}' if repo != '.' else ROOT
    if repo not in discovered:
        rows.append((repo, 'MISSING', '-', '-', '-'))
        continue
    _, branch, _ = git(cwd, 'branch', '--show-current')
    branch = branch or '(detached)'
    try:
        _, out, _ = git(cwd, 'rev-list', '--left-right', '--count', '@{upstream}...HEAD')
        behind, ahead = out.split()
        ab = f'{ahead}/{behind}'
    except Exception:
        ab = '-'
    _, porcelain, _ = git(cwd, 'status', '--porcelain')
    dirty = sum(1 for line in porcelain.splitlines() if not line.rstrip().endswith('calibration_data.json'))
    _, gitdir, _ = git(cwd, 'rev-parse', '--git-dir')
    _, commondir, _ = git(cwd, 'rev-parse', '--git-common-dir')
    gitdir_abs = os.path.normpath(os.path.join(cwd, gitdir))
    commondir_abs = os.path.normpath(os.path.join(cwd, commondir))
    if gitdir_abs.lower() != commondir_abs.lower():
        main_repo = os.path.dirname(commondir_abs)
        worktree_of = os.path.relpath(main_repo, ROOT).replace('\\\\', '/')
    else:
        worktree_of = '-'
    rows.append((repo, branch, ab, str(dirty), worktree_of))

w = max([len('REPO')] + [len(r[0]) for r in rows])
bw = max([len('BRANCH')] + [len(r[1]) for r in rows])
abw = max([len('AHEAD/BEHIND')] + [len(r[2]) for r in rows])
print('REPO'.ljust(w) + '  ' + 'BRANCH'.ljust(bw) + '  ' + 'AHEAD/BEHIND'.ljust(abw) + '  DIRTY  WORKTREE-OF')
for repo, branch, ab, dirty, wof in rows:
    print(f'{repo:<{w}}  {branch:<{bw}}  {ab:<{abw}}  {dirty:<5}  {wof}')
"
```

## Report

1. Relay the printed table verbatim.
2. Flag only rows where `DIRTY` > 0 or `AHEAD/BEHIND` isn't `0/0` (skip `-` rows — those have no upstream, not a problem to flag). A `MISSING` row is always worth flagging.
3. Note that `AHEAD/BEHIND` reflects the state as of the last fetch, not a live check — this skill never runs `git fetch`.
