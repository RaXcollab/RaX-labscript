---
name: check-sequence
description: Validate an experiment sequence before RunManager compilation — checks globals, device names, and basic structure
disable-model-invocation: true
---

Validate the experiment sequence file: $ARGUMENTS

If no file is specified, check the most recently modified `.py` file in `userlib/labscriptlib/Main_Experiment/sequences/`.

## Validation Steps

### 1. Read the sequence file
Read the target sequence file. Extract:
- All variable names that appear to be RunManager globals (used but not defined in the file or its imports)
- All device names referenced (e.g., `YAG1_line.go_high(...)`, `AO_channel.constant(...)`)
- The connection table import (should be `from labscriptlib.Main_Experiment.connection_table import connection_table`)

### 2. Read the connection table
Read `userlib/labscriptlib/Main_Experiment/connection_table.py`.
Extract all device names created inside the `connection_table()` function.

### 3. Check globals
Run the following to list all globals groups and their attributes:
```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python -c "
import h5py
with h5py.File('userlib/labscriptlib/Main_Experiment/Globals/BaF_globals.h5', 'r') as f:
    for group_name in f['globals']:
        group = f['globals'][group_name]
        print(f'Group: {group_name}')
        for attr in group.attrs:
            print(f'  {attr} = {group.attrs[attr]}')
"
```

### 4. Cross-check
Report:
- **Missing globals**: Variables used in the sequence that don't appear in any globals group
- **Missing devices**: Device names referenced in the sequence that aren't in the connection table
- **Stale references**: Device names in the sequence that exist in the connection table but under a different name (suggest correction)
- **Structure check**: Does the sequence have `connection_table()`, `start()`, and `stop(t)` calls?

### 5. Summary
Report PASS/WARN/FAIL with specific issues found. Note: some apparent "undefined" variables may be RunManager globals that are valid — check against the globals file before flagging.
