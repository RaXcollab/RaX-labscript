---
name: revert-to-main
description: Fetch all sub-repos in the labscript-suite workspace and switch each to its default branch (main or master), stashing uncommitted work first
disable-model-invocation: true
---

Bring every git working tree in the workspace to a clean state on its default branch without losing any in-progress work. Use after a session ends, before pulling, or when switching contexts.

## How repos are discovered

The skill walks the workspace and finds every directory containing a `.git` subdirectory, up to depth 3. Excludes:
- Non-directory `.git` entries (worktree pointers — they're files, not dirs).
- Anything under `worktrees/`, `node_modules/`, `__pycache__/`, `.ipynb_checkpoints/`.

Expected repos (CLAUDE.md "Repository Structure" + "External GUI Registry"):
```
.                       # labscript-suite (parent)
blacs
labscript-devices
labscript-utils
GUIs/HF_Locking
GUIs/rastering
GUIs/BigSkyControl
```

Auto-discovery will also find non-registered GUI repos (LabMonitoring, LakeshoreGUI, etc.). That's intended — all working trees get cleaned. Surface the full discovered list in the report so the user sees what was touched.

## How "without losing work" is guaranteed

- **Topic-branch commits** stay on their branch — `checkout` does not remove them. Branches ahead of `origin` remain ahead; recoverable via `git checkout <branch>`.
- **Uncommitted tracked changes** are saved with `git stash push -u -m "revert-to-main WIP <branch> <date>"`. Untracked files are included via `-u`.
- **Untracked files alone** are not branch-scoped — `checkout` does not touch them. No stash needed.
- **Push is never invoked.** Local-only commits stay local. (CLAUDE.md: "Do not push without asking.")

## Procedure

Run this from the workspace root. It auto-discovers, fetches, detects the default branch from `origin/HEAD`, stashes tracked changes if any, then checks out the default branch.

```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python -c "
import subprocess, datetime, os
ROOT = r'C:/Users/radmo/labscript-suite'
TODAY = datetime.date.today().isoformat()
EXCLUDED_DIRS = {'node_modules', '__pycache__', '.ipynb_checkpoints', 'worktrees'}
MAX_DEPTH = 3

def discover(root):
    repos = []
    for dp, dns, _ in os.walk(root):
        norm = dp.replace('\\\\', '/').rstrip('/')
        depth = 0 if norm == root.replace('\\\\', '/').rstrip('/') else norm[len(root):].count('/')
        dns[:] = [d for d in dns if d not in EXCLUDED_DIRS]
        if '.git' in dns and os.path.isdir(os.path.join(dp, '.git')):
            rel = os.path.relpath(dp, root).replace('\\\\', '/')
            repos.append('.' if rel == '.' else rel)
        if depth >= MAX_DEPTH - 1:
            dns[:] = []
    return sorted(repos, key=lambda p: (p != '.', p))

def git(cwd, *args):
    r = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

repos = discover(ROOT)
rows = []
for repo in repos:
    cwd = f'{ROOT}/{repo}' if repo != '.' else ROOT
    git(cwd, 'fetch', '--quiet', '--all', '--prune')
    rc, default_ref, _ = git(cwd, 'symbolic-ref', 'refs/remotes/origin/HEAD')
    default = default_ref.rsplit('/', 1)[-1] if rc == 0 else 'main'
    _, current, _ = git(cwd, 'branch', '--show-current')
    _, porcelain, _ = git(cwd, 'status', '--porcelain')
    tracked_dirty = any(not line.startswith('??') for line in porcelain.splitlines())
    actions = []
    if tracked_dirty:
        msg = f'revert-to-main WIP {current} {TODAY}'
        rc, _, err = git(cwd, 'stash', 'push', '-u', '-m', msg)
        actions.append(f'stashed: {msg!r}' if rc == 0 else f'STASH FAIL: {err}')
    if current == default:
        actions.append(f'already on {default}')
    else:
        rc, _, err = git(cwd, 'checkout', default)
        if rc == 0:
            actions.append(f'{current} -> {default} (topic branch retained)')
        else:
            actions.append(f'CHECKOUT FAIL: {(err.splitlines() or [\"\"])[0]}')
    rows.append((repo, default, '; '.join(actions)))

w = max(len(r[0]) for r in rows)
print(f'Discovered {len(rows)} repos:')
for repo, default, msg in rows:
    print(f'  {repo:<{w}}  [{default}]  {msg}')
"
```

## Report

After the script runs, summarize for the user:

1. **Default branch landed** per repo (one line each).
2. **Stashes created** (if any) — list the exact `git stash list` entries so the user can pop them: `git -C <repo> stash list | head -3`.
3. **Unexpected repos** — flag any repo found by auto-discovery that isn't in the CLAUDE.md registry, so the user can decide whether it should be registered or removed.
4. **Failures** — surface any `STASH FAIL` / `CHECKOUT FAIL` rows immediately; do not retry destructively.

## Safety

- Never `git reset --hard`, `git clean -fd`, or `git stash drop` here. The skill only fetches + stashes + checks out.
- A stash is recoverable indefinitely (`git stash list`, `git stash pop`). A reset is not.
- If a checkout fails (e.g., the default branch is in another worktree), report the error and stop. Do not force.
