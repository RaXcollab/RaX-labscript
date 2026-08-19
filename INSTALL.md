# Installing the RaX labscript suite

How to get from a bare Windows machine to a running RaX labscript stack, and how
to add the RaX fork to a machine that already runs stock labscript.

Sources this consolidates are listed in
[Where this came from](#where-this-came-from).

---

## 0. Which path are you on?

| Situation | Start at |
|---|---|
| **labscript is not installed at all** — bare machine, no conda env, no `~/labscript-suite` | [§2 Prerequisites](#2-prerequisites), then work straight through §3 → §7 |
| **Stock labscript already works** — you can launch BLACS and RunManager, and `~/labscript-suite` exists with a `labconfig` | Skip to [§5 Add the RaX repositories](#5-add-the-rax-repositories) |

Read [§1](#1-where-everything-goes) either way. Getting the directory structure
right is the single most important part of this install, and it is the easiest
thing to get wrong.

---

## 1. Where everything goes

### The one rule that matters

**The parent repo must be checked out at `%USERPROFILE%\labscript-suite`.**

`labscript_profile` resolves the profile directory as:

```python
LABSCRIPT_SUITE_PROFILE = Path("~" + getuser()).expanduser() / 'labscript-suite'
```

— `labscript-utils/labscript_profile/__init__.py:24`. It is hardcoded, with no
environment-variable override. On this machine that path is
`C:\Users\EBADI\labscript-suite`.

Two things follow. The folder must be named exactly `labscript-suite`, and it
must sit directly in your user profile directory — not one level deeper, and not
under its GitHub name `RaX-labscript`. If it is anywhere else, labscript will
create a fresh empty profile at the correct path and quietly use that instead,
and none of your `userlib` code will be importable.

If you want the working copy to live elsewhere, make a directory junction rather
than moving it (no administrator rights required):

```bat
mklink /J "%USERPROFILE%\labscript-suite" "D:\wherever\labscript-suite"
```

### The target tree

The parent repo *is* the profile folder. The three backend repos live inside it
as ordinary directories that the parent's `.gitignore` excludes — they are
**not** submodules, and each is committed and pushed separately. The `GUIs/`
folder is filed in the same place by convention but is not part of the suite
(§9).

```
%USERPROFILE%\labscript-suite\        <- RaXcollab/RaX-labscript  (parent repo)
├── userlib/                          <- tracked: devices, sequences, analysis
│   ├── user_devices/                 <- BigSkyHub, LaserLockDevice, RasteringDevice,
│   │                                    NuvuCamera, NI_SCOPE, RemoteControl, edge_counter
│   ├── labscriptlib/Main_Experiment/ <- this PC's sequences + connection table
│   ├── analysislib/Main_Experiment/  <- lyse analysis
│   ├── external_gui_lib/             <- shared ZMQ v2 server base
│   └── pythonlib/
├── docs/                             <- tracked reference docs
├── blacs/                            <- RaXcollab/blacs             (gitignored)
├── labscript-devices/                <- RaXcollab/labscript-devices (gitignored)
├── labscript-utils/                  <- RaXcollab/labscript-utils   (gitignored)
├── GUIs/                             <- NOT part of the suite; see §9  (gitignored)
│   ├── HF_Locking/                   <- separate application
│   ├── rastering/                    <- separate application
│   └── BigSkyControl/                <- separate application
├── labconfig/                        <- generated, per-machine      (gitignored)
├── app_saved_configs/                <- generated                   (gitignored)
└── logs/                             <- generated                   (gitignored)
```

The backend folder **names are fixed** — the developer install in §6
refers to `blacs`, `labscript-devices`, and `labscript-utils` by exact path, and
`CLAUDE.md` documents the `GUIs/` locations.

---

## 2. Prerequisites

| Prerequisite | Notes |
|---|---|
| **conda** (Miniconda or Anaconda) | Either works; labscript does not care which. See [Gotcha 6](#6-two-repo-scripts-hardcode-homeminiconda) about two repo scripts that assume `%USERPROFILE%\miniconda`. |
| **git**, on `PATH` | Needed at runtime as well as install time — see [Gotcha 3](#3-never-put-a-non-v-tag-on-a-backend-repo). |
| **`gh` CLI** (optional) | Convenient for cloning. The org is `RaXcollab` — not `RaXCollabs`. |
| Windows Terminal + `pwsh` | Only for `Launch Labscript.bat`. |
| Hardware SDKs | Only on machines with the hardware — see [§9](#9-hardware-drivers-and-sdks). |

If you need conda:

```bat
curl https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe -o miniconda.exe
start /wait "" miniconda.exe /S
del miniconda.exe
conda init
```

---

## 3. Install stock labscript

This section installs the unmodified labscript suite. Nothing here is
RaX-specific; the fork goes on top in §5–§6.

### 3a. Create the `labscript` conda environment

Build the environment from a yml **in one shot**. Do not assemble it
incrementally with repeated `conda install` calls — that is how the dependency
breakage recorded in the Confluence "Package dependence issue" page happened.

Use the tracked `environment.yml` at the repo root:

```bash
conda env create -f ./environment.yml
conda activate labscript
```

To change it later, edit the yml and run
`conda env update -f ./environment.yml --prune`.

`environment.yml` records the `labscript` environment as actually measured on
the lab control PC (see `.claude/session-handoff-2026-07-01-claude-setup.md`
§7–§8), which is the closest thing to an authoritative package list that exists
in-tree. The Confluence guide points at a `conda_list_output.txt` attachment for
this, but that attachment is not in the PDF export and not in this repo.

`old_environment.yml` and `old_fresh_environment.yml` are superseded and
disagree with the running environment — keep them only for archaeology.

> **The pins that matter.** `numpy=1.26.4` — NumPy >= 2.0 removes
> `np.string_()`, which `userlib/user_devices/NuvuCamera/blacs_workers.py`
> relies on. **pyzmq must not go to 26.x**, which breaks the internal
> inter-application sockets and kicks BLACS off its port.
>
> The exact pyzmq pin is genuinely unsettled. `CLAUDE.md` says `23.2.0` and "do
> NOT upgrade", but the running `labscript` environment measured **25.1.0** on
> 2026-07-01, and that handoff flags the mismatch as an open question. What is
> established is the 26.x ceiling. `environment.yml` carries 25.1.0 because that
> is what demonstrably runs — do not "correct" it to 23.2.0 without testing.

> **Refresh this file from the lab PC** rather than editing it by hand when the
> environment changes: `conda env export --from-history > environment.yml`.

**Every python command in this environment needs an explicit
`conda activate labscript` first.** On the lab control PC, bare `python` is the
wrong interpreter and `python3` hits the Windows Store shim.

### 3b. Create the profile

With the environment active:

```bash
labscript-profile-create
```

This creates `%USERPROFILE%\labscript-suite` and populates it with `userlib/`,
`labconfig/`, and `app_saved_configs/`, generates a `zprocess` shared-secret key,
and writes `labconfig/<HOSTNAME>.ini` (named from `socket.gethostname()`; on the
lab control PC that is `RaX-Control.ini`).

**Run this before bringing in the RaX repository**, which is the order §5
assumes. `create_profile()` raises `FileExistsError` if `userlib/`, `labconfig/`,
or `app_saved_configs/` already exists
(`labscript-utils/labscript_profile/create.py:63`), so if you clone the RaX repo
first — it ships a `userlib/` — you need the workaround in
[§5, alternatives B and C](#alternative-b-you-already-cloned-the-repo-and-it-is-not-at-the-profile-path).

### 3c. Create the application launchers

```bash
desktop-app install blacs runmanager runviewer lyse
```

At this point stock labscript should launch. Confirm it before going further.

---

## 4. Checkpoint

You should now have a working `~/labscript-suite` containing an example
`userlib/`, a `labconfig/<HOSTNAME>.ini`, `app_saved_configs/`, and four
launchable applications. Everything from here replaces the example `userlib`
with the RaX one and swaps three backend packages for the RaX forks.

---

## 5. Add the RaX repositories

### Alternative A: profile already created, no RaX clone yet (recommended)

The profile folder already exists and contains an example `userlib`, so you
cannot simply clone on top of it. Attach the repo's git history to the folder
instead:

```bash
cd "$USERPROFILE"
rm -rf labscript-suite/userlib          # example boilerplate; the repo ships the real one

git clone --no-checkout https://github.com/RaXcollab/RaX-labscript.git tmp-rax
mv tmp-rax/.git labscript-suite/.git
rmdir tmp-rax

cd labscript-suite
git checkout -f master
```

`labconfig/` and `app_saved_configs/` are gitignored, so the checkout leaves your
generated config untouched.

### Alternative B: you already cloned the repo, and it is *not* at the profile path

This is the easy case, and the one to steer toward. Because
`labscript-profile-create` always writes to `%USERPROFILE%\labscript-suite`
regardless of your working directory, a clone sitting anywhere else does not
collide with it at all. Generate the profile, take the two generated
machine-specific folders, and move the clone into place:

```bash
conda activate labscript
labscript-profile-create                       # creates a clean %USERPROFILE%\labscript-suite

cd /path/to/your/clone                         # wherever you cloned it
mv "$USERPROFILE/labscript-suite/labconfig"          .
mv "$USERPROFILE/labscript-suite/app_saved_configs"  .

rm -rf "$USERPROFILE/labscript-suite"          # the generated profile; only example userlib is left in it
cd .. && mv <your-clone-dir> "$USERPROFILE/labscript-suite"
```

`labconfig/` (which also holds the generated `zprocess` shared-secret key) and
`app_saved_configs/` are both gitignored, so they drop into the clone without
touching tracked files.

> Verify before the `rm -rf`: the only thing left in the generated profile at
> that point should be the example `userlib/`. If `labconfig/` is still there,
> the two `mv` lines did not run — stop and check, rather than deleting the
> labconfig you just generated.

### Alternative C: the clone is already sitting at `%USERPROFILE%\labscript-suite`

Here the collision is real, because the clone ships a `userlib/`. Park it, run
profile-create, then restore:

```bash
cd "$USERPROFILE/labscript-suite"
conda activate labscript

test -e userlib.repo && { echo "userlib.repo exists — resolve by hand, do not continue"; }
mv userlib userlib.repo          # park the tracked tree
labscript-profile-create         # writes labconfig/, app_saved_configs/, userlib/
rm -rf userlib                   # the generated example boilerplate ONLY
mv userlib.repo userlib          # restore the tracked tree
```

> **Run this once, and check each line.** The sequence is not idempotent: on a
> second run `mv userlib userlib.repo` fails because `userlib.repo` already
> exists, `labscript-profile-create` then fails because `userlib` still exists,
> and the `rm -rf userlib` that follows would delete **the real tracked tree**
> rather than generated boilerplate. If any line errors, stop there. Prefer
> alternative B — move the clone out of the profile path first and you never
> touch this sequence.

### Then, either way: the three backend forks

From the parent directory:

```powershell
.\bootstrap.ps1
```

`repos.yml` records each backend's URL, branch, and pinned commit;
`bootstrap.ps1` clones all three into place at those commits. This is what makes
the install reproducible — without it a fresh clone picks up whatever happens to
be on each fork's default branch that day, which is not necessarily a set that
works together.

The script is safe to re-run, and never discards uncommitted work: a backend with
a dirty working tree is reported and skipped.

| Command | Effect |
|---|---|
| `.\bootstrap.ps1` | Clone/update all three to their **pinned** commits (detached HEAD) |
| `.\bootstrap.ps1 -Latest` | Check out each backend's **branch tip** instead — the normal development state |
| `.\bootstrap.ps1 -Install` | Sync, then run the editable install from §6 |
| `.\bootstrap.ps1 -UpdatePins` | Record the current backend HEADs as the new pins in `repos.yml` |

After a plain `.\bootstrap.ps1` the backends sit at a detached commit, which is
right for reproducing a known-good state but not for development. Run
`.\bootstrap.ps1 -Latest` to put them back on their branches before you start
committing to them.

When you land a parent change that depends on new backend behaviour, run
`.\bootstrap.ps1 -UpdatePins` and commit `repos.yml` alongside it. That keeps the
recorded set honest instead of drifting the way the hand-written snapshot in
`docs/stable-snapshot-2026-06-09.md` did.

Equivalent by hand, if you would rather not run the script:

```bash
cd "$USERPROFILE/labscript-suite"
gh repo clone RaXcollab/blacs
gh repo clone RaXcollab/labscript-devices
gh repo clone RaXcollab/labscript-utils
```

These three plus the parent are the whole suite. The external GUI applications
under `GUIs/` are **not** part of this install — see [§9](#9-external-guis).

**Clone full history — never `--depth`.** The backend packages compute their
version with `setuptools_scm` at import time, which needs the tag history.

`gh repo clone` adds an `upstream` remote pointing at `shafinulh/*` on the four
forked repos. That is harmless and useful for pulling upstream changes; `origin`
is the RaXcollab fork and is what you push to.

---

## 6. Developer install of the RaX forks

With the `labscript` env active, from `~/labscript-suite`:

```bash
pip install --no-build-isolation --no-deps -e blacs -e labscript-devices -e labscript-utils
```

Only these three are forked. The Confluence guide's wider form
(`-e labscript -e runmanager -e lyse -e runviewer ...`) generally fails, because
those four are unmodified and already installed from the environment.

The two flags mean pip will neither fetch build dependencies nor re-resolve
runtime ones — both sets are expected to be in the environment already, which
they are once §3a has run. If this step fails, see
[Troubleshooting](#troubleshooting).

This must come **after** §3a, never before it.

---

## 7. Configure labconfig

Edit `labconfig/<HOSTNAME>.ini` for this machine:

```ini
[DEFAULT]
apparatus_name = Main_Experiment
shared_drive = C:
experiment_shot_storage = C:\Users\<user>\MIT Dropbox\...\Experiments\Main_Experiment
userlib = %(labscript_suite)s\userlib
labscriptlib = %(userlib)s\labscriptlib\%(apparatus_name)s
analysislib = %(userlib)s\analysislib\%(apparatus_name)s
user_devices = user_devices

[paths]
connection_table_py = %(labscriptlib)s\connection_table.py
```

`labconfig/` is gitignored — it is per-machine and never pushed.

Then compile `userlib/labscriptlib/Main_Experiment/connection_table.py` in
RunManager and restart BLACS so it picks up the new table.

---

## 8. Post-install

**Pre-push hook** (one-time per checkout — git will not share hooks through the
working tree):

```bash
cp .githooks/pre-push .git/hooks/pre-push && chmod +x .git/hooks/pre-push
```

It runs `userlib/user_devices/*/tests/` in the `labscript` env and blocks the
push on failure. Log: `.git/hooks/pre-push.log`. `bash .git/hooks/pre-push` is
also the manual full-suite runner. Note it skips silently — allowing the push —
if it cannot find conda at `$HOME/miniconda`, so a green push does not by itself
prove the tests ran.

**Launcher.** `Launch Labscript.bat` opens Windows Terminal with BLACS,
RunManager, and lyse in three panes. It requires `wt` and `pwsh`, and expects
conda at `%USERPROFILE%\miniconda` (see [Gotcha 6](#6-two-repo-scripts-hardcode-homeminiconda)).

---

## 9. External GUIs

**These are not part of the labscript suite and not part of this install.** They
are independent applications that happen to talk to BLACS over ZMQ. They live in
their own repositories, run in their own conda environments, and are installed
and updated separately from everything above. A labscript install is complete and
correct without them.

By convention on the lab control PC they are checked out under `GUIs/` inside the
labscript-suite folder, which the parent's `.gitignore` excludes. That is a
filing convention, not a dependency.

**Each GUI documents its own environment, dependencies, and launch command
internally** — consult that repository's `README.md` and `CLAUDE.md`. Do not
expect the `labscript` environment to run any of them.

| GUI | BLACS device class | REQ-REP | PUB-SUB | Connection-table name |
|---|---|---|---|---|
| `GUIs/HF_Locking` | `LaserLockDevice` | 3796 | 3797 | `LaserLockGUI` |
| `GUIs/rastering` | `RasteringDevice` | 55535 | 55536 | `RasteringGUI` |
| `GUIs/BigSkyControl` | `BigSkyHub` | 55540 | 55541 | `BigSkyLasers` |

Start each GUI before the BLACS tab that talks to it. Protocol reference:
`docs/remotecontrol-zmq-protocol-v2.md` (v1 is deprecated and refused by v2
servers).

---

## 10. Hardware drivers and SDKs

Needed only on machines with the corresponding hardware, and not resolvable from
the environment file above.

| Component | Requirement |
|---|---|
| NI DAQ cards | NI-DAQmx driver runtime, accessed through **PyDAQmx** and the labscript-devices `NI_DAQmx` driver. Note the `nidaqmx` pip package is deliberately *not* installed — it did not appear in the lab environment's `pip list`. |
| NI scope (`NI_SCOPE`) | NI-SCOPE driver runtime + `niscope` (imported by `userlib/user_devices/NI_SCOPE`) |
| Nuvu camera | SDK vendored at `userlib/user_devices/NuvuCamera/Nuvu_sdk/` |

GUI-side hardware (HighFinesse wavemeter, Thorlabs KCubes, IDS uEye camera,
BigSky YAG serial link) is documented in each GUI's own repo per §9.

---

## 11. Verification

```bash
conda activate labscript
python -c "import labscript_utils; print(labscript_utils.__version__)"   # e.g. 3.3.0rc1.dev30+...
python -c "from labscript_profile import LABSCRIPT_SUITE_PROFILE as p; print(p)"
python -c "import blacs, labscript_devices; print('backends ok')"
python -c "import user_devices; print('userlib on path')"
pip list | grep -E "labscript|pyzmq|numpy"   # expect editable paths, pyzmq 23.2.0, numpy 1.26.4
```

The second line must print `%USERPROFILE%\labscript-suite`. The fourth proves
`userlib` is on `sys.path`.

Then: compile the connection table in RunManager -> start BLACS -> check
`logs/BLACS.log` -> run one test shot and open the resulting h5 in HDFView.

---

## Gotchas

### 1. The profile path is hardcoded

`~/labscript-suite`, no override, and a wrong location fails silently by
auto-creating an empty profile. See §1. This is the most common way to end up
with a stack that imports but cannot find any of your devices.

### 2. Profile creation must precede the RaX `userlib`

`labscript-profile-create` refuses to run if `userlib/`, `labconfig/`, or
`app_saved_configs/` already exists. The documented order — environment, then
profile, then pull the repo — avoids this entirely. Only a clone-first order
runs into it, and even then only if the clone is sitting at the profile path
already. §5 alternative B avoids it entirely by generating the profile while the
clone is elsewhere; alternative C is the guarded workaround if you are already
stuck at the profile path.

### 3. Never put a non-`v*` tag on a backend repo

`labscript_utils/__version__.py:15-17` checks for a `.git` directory and, finding
one, calls `setuptools_scm.get_version()` at **import** time rather than build
time. A non-`v*` tag reachable from HEAD in `blacs`, `labscript-devices`, or
`labscript-utils` makes `git describe` return it, the version parse asserts,
`import labscript_utils` raises, and BLACS and RunManager will not start.

This is not a hazard of installing — it is a maintenance rule. It took the lab
down on 2026-06-10 when `stable/...` tags were restored on the backend repos;
the incident is written up in `docs/stable-snapshot-2026-06-09.md`, which is also
where the known-good per-repo commit hashes live. Pin backend baselines by commit
hash, not tag.

The same mechanism is why clones need full tag history and why `git` must stay on
`PATH` at runtime.

### 4. Commit each repo separately

The suite is four repos — parent plus three backends — and each takes its own
commit. The parent's `.gitignore` excludes `blacs/`, `labscript-devices/`,
`labscript-utils/`, `GUIs/`, `labconfig/`, `logs/`, and `app_saved_configs/`, so
a clean `git status` in the parent tells you nothing about the state of the
backends (or of anything filed under `GUIs/`).

### 5. Ownership moved from `shafinulh` to `RaXcollab`

Older documentation — including the Confluence export — says to clone from
`shafinulh/RaX-labscript`, `shafinulh/blacs`, and so on. Those are the historical
upstreams. `RaXcollab/*` is authoritative now. Where the official labscript
documentation disagrees with our fork's code, **the fork's code wins**.

### 6. Conda location is auto-detected, not assumed

labscript itself is indifferent to whether you use Miniconda or Anaconda, and to
where it is installed. Four scripts in this repo used to assume
`%USERPROFILE%\miniconda` (or one specific user's profile) and would silently do
nothing on anyone else's machine. They now resolve conda at run time — via
`$CONDA_EXE`, then `conda` on `PATH`, then the usual install locations:

- `Launch Labscript.bat`
- `.githooks/pre-push`
- `.claude/hooks/check-py-syntax.ps1` (through `.claude/hooks/_conda-path.ps1`)
- `.claude/backup-memory.sh` (derives its path from the checkout, not a username)

If detection fails, the launcher reports it and stops; the hooks fail open. To
force a specific installation, export `CONDA_EXE` before running them.

Note that `.githooks/pre-push` **skips the tests and allows the push** when it
finds no conda at all, so a green push on a machine without the `labscript`
environment does not mean the tests ran.

### 7. Do not mix `conda install` and `pip install`

Use conda first and pip only when necessary, and avoid installing core scientific
libraries (`numpy`, `scipy`, `h5py`) with pip inside the conda environment — pip
will replace a conda-built `numpy` with a potentially incompatible PyPI one.

### 8. `GUIs/rastering/calibration_data.json` is live operator data

It churns constantly, and a dirty working tree there is normal. Commit it as
churn; **never `git restore` it** — that wipes the live calibration.

### 9. `.gitmodules` is inert

The parent repo carries a `.gitmodules` declaring the three backends as
submodules of `shafinulh/*`, but the submodules were never registered:
`git ls-files -s | awk '$1=="160000"'` returns nothing, and the same paths are
listed in `.gitignore`. The backends are plain ignored directories holding
independent clones, exactly as `CLAUDE.md` describes. The file is a leftover from
the repo's first commit and can be ignored.

---

## Troubleshooting

**`import h5py` fails with a DLL load error.** The conda build of `h5py` pulled
in by the conda `labscript-suite` package is the known-bad one, documented on the
Confluence "Package dependence issue" page. Drop `labscript-suite` from the yml,
create the environment with just python/pyzmq/numpy/pyqt/pip, then run
`pip install labscript-suite` inside it — pip resolves `h5py` from the right
source. Keep the `pyzmq` pin either way.

**Step 6 fails complaining about build backends.** `--no-build-isolation` means
pip will not download build dependencies. The backends declare
`requires = ["setuptools>=64", "wheel", "setuptools_scm>=8"]` in their
`pyproject.toml`. These normally come with the environment already —
`setuptools_scm` is a runtime dependency of `labscript-utils`, and conda provides
`setuptools` and `wheel` alongside `pip` — but if the environment was built
unusually, add them:
`conda install -n labscript "setuptools>=64" wheel "setuptools_scm>=8"`.

**Sequences cannot import `user_devices`.** The `labscript-suite.pth` file that
`labscript-utils` installs into site-packages is what puts `userlib` and
`pythonlib` on `sys.path`, using the paths from your `labconfig`. Check that
`python -c "import user_devices"` works in the `labscript` env, that `labconfig`
points at the right `userlib`, and that you are not pointed at an accidentally
auto-generated profile — `import labscript_utils` silently creates an empty one
if `~/labscript-suite` is missing.

---

## Where this came from

| Source | What it holds |
|---|---|
| `Labscript-Confluence-2026-02-11.pdf` | "Installation Guide" (pp. 22-25), "GitHub Sync of labscript-suite Folder" (pp. 11-13), "Package dependence issue for installing labscript" (p. 51) |
| `CLAUDE.md` | Current env pins, repo table, critical conventions, external-GUI registry |
| `.claude/session-handoff-2026-07-01-claude-setup.md` §7–§8 | The `labscript` environment as actually measured on the lab PC — the basis for `environment.yml` |
| `old_fresh_environment.yml` / `old_environment.yml` | Superseded env spec / frozen full export, kept for archaeology |
| `docs/stable-snapshot-2026-06-09.md` | Known-good per-repo commit hashes; the setuptools_scm tag incident |
| `GUIs/*/README.md`, `GUIs/*/CLAUDE.md` | Each GUI's own environment, dependencies, and launch command |
| `.githooks/pre-push` | Hook install contract |
| `labscript-utils/labscript_profile/` | Profile path resolution and `labscript-profile-create` behaviour |
