# Install the RaX labscript suite

**Status:** Current installation authority
**Last reviewed:** 2026-08-21
**Validation:** Repository checks are complete. Clean-machine and lab hardware tests remain pending.

RaX uses the official labscript suite as its package base. Three editable RaX forks replace the stock backend packages.

The active forks are `blacs`, `labscript-devices`, and `labscript-utils`. `repos.yml` records their tested commits.

This guide supports 64-bit Windows. Use PowerShell for all repository commands.

## 1. Select an installation path

Use **Path A** when labscript is not installed.

Use **Path B** when an official labscript environment already exists.

Path B can preserve the official environment. Clone that environment before you install the RaX overrides.

An environment cannot select stock and RaX copies of the same backend. Editable RaX packages become active in that environment.

## 2. Keep source code separate from the profile

Clone this repository into any source directory except `%USERPROFILE%\labscript-suite`.

The labscript profile remains at `%USERPROFILE%\labscript-suite`. It contains machine configuration, logs, secrets, and saved application state.

Never replace an existing profile with this repository. Never delete an existing collaborator `userlib`.

The source checkout has this structure after bootstrap:

```text
RaX-labscript\
  bootstrap.ps1
  environment.yml
  repos.yml
  userlib\
  blacs\
  labscript-devices\
  labscript-utils\
```

The three backend directories are separate Git repositories. The parent repository does not use Git submodules.

## 3. Install prerequisites

Install these items before either path:

- 64-bit Windows 10 or Windows 11
- PowerShell 5.1 or later
- Git for Windows
- A conda distribution with Anaconda PowerShell Prompt
- Network access to `github.com` and the configured conda channels

Do not use the conda `base` environment for labscript.

The environment includes these direct development requirements:

- `setuptools>=64`
- `setuptools-scm>=8`
- `wheel`
- `pytest`

### Base hardware prerequisites

Install the National Instruments NI-DAQmx runtime before you use NI DAQ hardware.

Install a compatible PyDAQmx package in the selected environment. The stock labscript packages normally provide it.

Load compatible PrawnBlaster firmware onto the Raspberry Pi Pico. Record its assigned serial port.

Install the 64-bit NI-SCOPE driver before you use an NI oscilloscope.

Install the NI `niscope` Python API in the selected environment. Path A installs it from `environment.yml`.

The RaX reference connection table uses these devices:

- PrawnBlaster pseudoclock
- NI PXIe-6361
- NI PXIe-6535
- NI-SCOPE device integration

### Integration scaffolding

The repository also provides interface devices for these external applications:

- Laser lock
- Raster controller
- BigSky YAG controller

Their GUI applications remain separate programs. This installer does not install their environments or hardware dependencies.

Nuvu support remains optional. It does not block the base installation.

## 4. Clone the RaX source

Choose a source parent that is not the labscript profile.

```powershell
$sourceParent = Join-Path $env:USERPROFILE 'src'
New-Item -ItemType Directory -Force -Path $sourceParent | Out-Null
Set-Location $sourceParent
git clone https://github.com/RaXcollab/RaX-labscript.git
Set-Location RaX-labscript
```

Run all remaining repository commands from this checkout.

## 5. Path A: labscript is not installed

Open Anaconda PowerShell Prompt.

Create the RaX environment from the repository specification.

```powershell
conda env create --name labscript-rax --file environment.yml
conda activate labscript-rax
```

Fetch the pinned RaX backends and install them as editable packages.

```powershell
.\bootstrap.ps1 -Install -EnvironmentName labscript-rax
```

Create a profile only when one does not exist.

```powershell
if (-not (Test-Path (Join-Path $env:USERPROFILE 'labscript-suite\labconfig'))) {
    labscript-profile-create
}
```

Open `%USERPROFILE%\labscript-suite\labconfig\<computer-name>.ini`.

Set `userlib` to the absolute path of this checkout's `userlib` directory.

Use these values as a template:

```ini
[DEFAULT]
apparatus_name = Main_Experiment
userlib = C:\path\to\RaX-labscript\userlib
pythonlib = %(userlib)s\pythonlib
labscriptlib = %(userlib)s\labscriptlib\%(apparatus_name)s
analysislib = %(userlib)s\analysislib\%(apparatus_name)s
```

Keep machine secrets and saved application state inside the profile.

## 6. Path B: official labscript already exists

First, identify the existing environment name.

```powershell
conda env list
```

### Recommended: preserve the official environment

The next example assumes that the existing environment is named `labscript`.

```powershell
conda create --name labscript-rax --clone labscript
conda activate labscript-rax
conda install "setuptools>=64" "setuptools-scm>=8" wheel pytest
python -m pip install niscope
.\bootstrap.ps1 -Install -EnvironmentName labscript-rax
```

This method keeps the original package environment intact. Both environments still use the same default labscript profile.

Do not run both application stacks at the same time. They can compete for the same ports and saved state.

Leave the existing profile and `userlib` unchanged for a backend-only installation.

To use the RaX reference apparatus, set the profile `userlib` path to the RaX checkout. Make this change explicitly.

Do not automate a merge between two `userlib` directories. Resolve each file conflict with its owner.

### Advanced: override the existing environment directly

Use this option only when the official backend packages do not need to remain active.

```powershell
conda activate labscript
conda install "setuptools>=64" "setuptools-scm>=8" wheel pytest
python -m pip install niscope
.\bootstrap.ps1 -Install -EnvironmentName labscript
```

This operation leaves the profile unchanged. It makes the three editable RaX backends active in the selected environment.

## 7. Configure the RaX reference apparatus

The reference apparatus is an example, not a portable hardware configuration.

Review these fields before you compile its connection table:

- PrawnBlaster serial port
- NI Measurement and Automation Explorer device names
- NI-SCOPE resource name and channel settings
- NI clock terminals
- External GUI hostnames and ports
- Shot storage path
- Apparatus name

The current reference uses `COM4`, `PXI1Slot8`, and `PXI1Slot5`. Change them for another machine.

Use localhost for GUI scaffolding when each external GUI runs on the same computer.

## 8. Configure launch commands and Git hooks

Install official desktop shortcuts from the selected environment when required.

```powershell
desktop-app install blacs lyse runmanager runviewer
```

The repository launcher accepts an environment name.

```powershell
& '.\Launch Labscript.bat' labscript-rax
```

Use the tracked pre-push hook for development checkouts.

```powershell
git config core.hooksPath .githooks
git config rax.labscriptEnv labscript-rax
```

The hook runs user-device tests from the configured environment.

## 9. Verify the installation

Activate the selected environment.

```powershell
conda activate labscript-rax
```

Check package dependencies.

```powershell
python -m pip check
```

Check backend provenance.

```powershell
python -c "import blacs, labscript_devices, labscript_utils; print(blacs.__file__); print(labscript_devices.__file__); print(labscript_utils.__file__)"
```

Each printed path must point into the RaX source checkout.

Check the pinned backend commits.

```powershell
git -C blacs rev-parse HEAD
git -C labscript-devices rev-parse HEAD
git -C labscript-utils rev-parse HEAD
```

Compare each value with `repos.yml`.

Check the profile and `userlib` path.

```powershell
python -c "import labscript_profile; print(labscript_profile.LABSCRIPT_SUITE_PROFILE); print(labscript_profile.default_labconfig_path())"
python -c "import user_devices; print(list(user_devices.__path__))"
python -c "import niscope; print(niscope.__version__)"
```

Run the repository tests.

```powershell
python -m pytest -q userlib\user_devices
```

Check the current pyzmq version without changing it.

```powershell
python -c "import zmq; print(zmq.__version__)"
```

The repository pins pyzmq 25.1.0. Treat this pin as provisional until lab computer validation is complete.

When the system is idle, start BLACS and inspect its log.

Use the normal lab procedure for one controlled test shot. Confirm that the shot creates the expected HDF5 file.

## 10. Maintain backend pins

Use the pinned commits for installations.

```powershell
.\bootstrap.ps1
```

Use branch tips only for deliberate development work.

```powershell
.\bootstrap.ps1 -Latest
```

After validation, record new full commit identifiers.

```powershell
.\bootstrap.ps1 -UpdatePins
```

Commit `repos.yml` with the parent change that requires the new backend state.

## 11. Troubleshooting

### Bootstrap reports a dirty checkout

Commit, stash, or discard the backend changes. Run bootstrap again after the working tree is clean.

Bootstrap never replaces a dirty backend during installation.

### A backend imports from the conda environment

Run `bootstrap.ps1 -Install` from the selected RaX environment. Check the module paths again.

### `user_devices` does not import

Check the host labconfig file. Confirm that `userlib` points to the intended absolute path.

### NI devices do not initialize

Confirm the NI-DAQmx runtime with NI Measurement and Automation Explorer. Confirm each configured device name and terminal.

Confirm the NI-SCOPE runtime and resource name. Confirm that `python -c "import niscope"` succeeds.

### PrawnBlaster does not initialize

Confirm its firmware and serial port. Update the connection table for the assigned port.

## 12. Validation status

The repository has verified full backend pins and safe dirty-tree handling.

The following release gates remain open:

- Clean Windows installation
- Existing-profile preservation test
- Lab control computer package record
- BLACS startup test
- Controlled hardware shot
- Clean-history export and secret scan before public release

Do not describe the installation as validated until all six gates pass.

## Upstream references

- [Official conda environment setup](https://github.com/labscript-suite/labscript-suite/blob/master/docs/source/installation/setting-up-an-environment.rst)
- [Official conda installation](https://github.com/labscript-suite/labscript-suite/blob/master/docs/source/installation/regular-anaconda.rst)
- [NI-SCOPE driver download](https://www.ni.com/en/support/downloads/drivers/download.ni-scope.html/)
- [NI Python instrument APIs](https://github.com/ni/nimi-python)
