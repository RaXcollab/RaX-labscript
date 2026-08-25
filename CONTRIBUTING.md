# Contribute to RaX labscript

**Status:** Current contributor procedure
**Last reviewed:** 2026-08-21

This project uses one parent repository and three independent backend repositories.

## Repository ownership

Use the parent repository for these changes:

- `userlib` devices, sequences, and analysis
- Installation files
- Backend pins
- Shared documentation

Use the applicable backend repository for backend package changes:

- `blacs`
- `labscript-devices`
- `labscript-utils`

The parent repository ignores backend directories. Parent `git status` does not report their changes.

## Prepare a checkout

Follow [INSTALL.md](INSTALL.md) before development.

Activate the selected RaX environment.

```powershell
conda activate labscript-rax
```

Install the tracked Git hook.

```powershell
git config core.hooksPath .githooks
git config rax.labscriptEnv labscript-rax
```

## Change a backend

Create the feature branch inside the affected backend repository.

Commit and test that backend before you update the parent pin.

After validation, record the full backend commit identifiers.

```powershell
.\bootstrap.ps1 -UpdatePins
```

Commit `repos.yml` with each parent change that depends on the backend commit.

Do not create a backend tag unless you prepare a backend release.

## Test a change

Run the focused test for the changed component first.

Run all portable user-device tests before push.

```powershell
python -m pytest -q userlib\user_devices
```

Check dependency state after package changes.

```powershell
python -m pip check
```

Compile the selected connection table after device or sequence changes.

Use the approved lab procedure for hardware tests. Record the tested machine and package versions.

## Write documentation

Replace obsolete statements when behavior changes. Do not append corrections to old statements.

Keep one current authority for each procedure or contract.

Add `Status` and `Last reviewed` metadata to maintained documents.

Use repository-relative links. Do not add personal paths, hostnames, email addresses, or machine-local permissions.

Keep session handoffs, generated agent memory, and private operator notes outside the shared repository.

## Update installation requirements

Add direct runtime, build, or test dependencies to `environment.yml`.

Do not depend on an unrecorded transitive package.

Mark untested versions as provisional. Validate them on a clean machine before release.

## Submit a parent change

Confirm these items before review:

- Parent working tree contains only intended changes.
- Each modified backend has its own commit.
- `repos.yml` contains full backend commit identifiers.
- Portable tests pass.
- Documentation describes current behavior.
- No generated output or machine-specific state is tracked.
