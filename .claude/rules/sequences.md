---
paths:
  - "userlib/labscriptlib/**"
---

# Sequence & Connection Table Conventions

- **Never assert timing behavior without reading source.** Labscript timing (Shutter delays, t=0 clamping, ramp interpolation) has non-obvious constraints. Read the class implementation before claiming what happens at specific times
- **Connection table import pattern:** Device instantiation wrapped in `def connection_table():`, not module-level. Sequences call `from labscriptlib.Main_Experiment.connection_table import connection_table; connection_table()`. Required because `sys.modules` caching + `compiler.reset()` between compiles.
- BLACS loads only `connection_table.py` — other connection table files are backups
- **RunManager globals** (`tYAG`, `tstart`, `DOUBLE_YAG`, etc.) are injected at compile time from `Globals/BaF_globals.h5` — not undefined variables
- **Connection table does NOT have access to RunManager globals** — globals are injected into *sequences* at compile time, not into `connection_table.py`. Device parameters like `num_lasers` must be hardcoded or read from `labconfig`.
- **ENABLED switchboard**: `connection_table.py` gates each BLACS tab behind a module-level `ENABLED` dict (PrawnBlaster excepted — always on). Workflow: flip flag → recompile CT → restart BLACS. Even-DO padding is automatic (`_pad_even_digitals`); never add manual dummy DO lines.
  - Sequences may **read** `ENABLED` (`from labscriptlib.Main_Experiment.connection_table import ENABLED`) to branch on hardware presence — **never assign to it**: a mutated dict compiles a subset CT that BLACS accepts silently, and the omitted device's tab is left stranded in POST_EXP mid-queue
  - **After disabling a device**: recompile any shots queued against the old CT (BLACS rejects them), and its saved front-panel values are lost on the next clean BLACS exit
- Old sequences in the directory are reference for past experiments — don't archive or delete
- Configuration evolves with the experiment — don't assume device counts or channel names are fixed

## Do NOT Flag

- **RunManager globals** appearing "undefined" in sequences — injected at compile time
- **Connection table parameters** differing from hardware maximums — reflect current experiment, not hardware limits