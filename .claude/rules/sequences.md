---
paths:
  - "userlib/labscriptlib/**"
---

# Sequence & Connection Table Conventions

- **Connection table import pattern:** Device instantiation wrapped in `def connection_table():`, not module-level. Sequences call `from labscriptlib.Main_Experiment.connection_table import connection_table; connection_table()`. Required because `sys.modules` caching + `compiler.reset()` between compiles.
- BLACS loads only `connection_table.py` — other connection table files are backups
- **RunManager globals** (`tYAG`, `tstart`, `DOUBLE_YAG`, etc.) are injected at compile time from `Globals/BaF_globals.h5` — not undefined variables
- Old sequences in the directory are reference for past experiments — don't archive or delete
- Configuration evolves with the experiment — don't assume device counts or channel names are fixed

## Do NOT Flag

- **RunManager globals** appearing "undefined" in sequences — injected at compile time
- **Connection table parameters** differing from hardware maximums — reflect current experiment, not hardware limits

## Timing Safety

- **Never assert timing behavior without reading source.** Labscript timing (Shutter delays, t=0 clamping, ramp interpolation) has non-obvious constraints. Read the class implementation before claiming what happens at specific times