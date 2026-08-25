# RaX labscript suite

**Status:** Current project context
**Last reviewed:** 2026-08-24

## Repository structure

This parent repository contains the RaX `userlib` reference apparatus and shared installation files.

The `blacs`, `labscript-devices`, and `labscript-utils` directories are separate repositories.

Commit changes in each repository separately. Update `repos.yml` after a validated backend change.

## Supported scope

The base system supports PrawnBlaster, NI DAQmx, and NI-SCOPE hardware.

The repository includes generic laser-lock, raster, and YAG integration devices.

Independent GUI repositories and their environments remain outside the core installation.

## Local configuration

Keep hardware identifiers, ports, shot storage, secrets, and saved state in the local labscript profile.

Keep machine permissions in ignored `.claude/settings.local.json`.

Follow `INSTALL.md` for environment and profile configuration.

## Safety and verification

Ask before destructive filesystem or Git actions.

Do not create non-`v*` tags in backend repositories.

Use the applicable test procedure before you change a backend pin.

Use the approved lab procedure for hardware tests.

## References

- `README.md`
- `INSTALL.md`
- `CONTRIBUTING.md`
- `docs/index.md`
- `docs/remotecontrol-zmq-protocol-v2.md`
