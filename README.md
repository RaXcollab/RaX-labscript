# RaX labscript

**Status:** Active RaX fork
**Last reviewed:** 2026-08-21

This repository contains the RaX labscript integration layer and reference apparatus.

It also records exact versions for three modified labscript backend repositories.

## Scope

The core repository contains:

- RaX `userlib` devices, sequences, and analysis code
- A reference `Main_Experiment` apparatus
- Pinned RaX forks of `blacs`, `labscript-devices`, and `labscript-utils`
- Installation and contributor procedures
- Current protocol, architecture, and data-contract documents

External GUI applications are separate programs. This repository contains only their labscript-side interfaces and shared contracts.

## Installation

Read [INSTALL.md](INSTALL.md) before you clone backend repositories or change an environment.

The guide provides two supported paths:

1. Create a new stock package base with RaX editable overrides.
2. Add RaX overrides to an existing official labscript installation.

The recommended existing-install path clones the conda environment first. It never deletes or replaces the existing profile or `userlib`.

## Source and machine data

Keep the source checkout separate from `%USERPROFILE%\labscript-suite`.

The profile directory contains machine configuration, logs, saved state, secrets, and shot paths.

The source repository contains portable code and documented reference values.

## Base hardware target

The initial collaborator installation supports:

- PrawnBlaster pseudoclock
- NI PXIe-6361
- NI PXIe-6535
- NI-DAQmx through PyDAQmx
- NI-SCOPE through the NI `niscope` Python API
- Laser-lock interface scaffolding
- Raster interface scaffolding
- BigSky YAG interface scaffolding

Nuvu support remains optional.

## Repository layout

```text
RaX-labscript\
  userlib\                 RaX apparatus and integration code
  docs\                    Current technical documentation
  bootstrap.ps1            Pinned backend checkout and install
  environment.yml          Direct conda environment specification
  repos.yml                Full backend commit identifiers
  INSTALL.md               Installation authority
  CONTRIBUTING.md          Multi-repository contributor workflow
```

The backend directories appear after bootstrap. Git ignores them in the parent repository because each directory has its own history.

## Current technical documents

Use [docs/index.md](docs/index.md) as the documentation entry point.

Important contracts include:

- [BLACS state machine](docs/blacs-state-machine.md)
- [BLACS device patterns](docs/blacs-device-patterns.md)
- [RemoteControl ZMQ protocol v2](docs/remotecontrol-zmq-protocol-v2.md)
- [Shot HDF5 layout](docs/shot-h5-layout.md)
- [Main experiment overview](docs/main-experiment-overview.md)
- [External GUI architecture](docs/external-guis-architecture.md)

## Sharing status

The current tree removes known personal paths, generated state, and private operator notes.

Git history still contains removed files.

Share it only with trusted collaborators until you complete the [public sharing procedure](docs/public-sharing.md).

## Validation status

Repository-level portability checks are in progress.

The release still requires a clean Windows installation and lab hardware validation.

Do not describe this branch as a validated release until the gates in [INSTALL.md](INSTALL.md#12-validation-status) pass.
