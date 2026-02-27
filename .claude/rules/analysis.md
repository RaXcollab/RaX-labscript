---
paths:
  - "userlib/analysislib/**"
---

# Analysis Conventions

## Do NOT Flag

- **NaN rows in NI_SCOPE h5 datasets** — unsaved channels are NaN-filled intentionally (selective saving), not data corruption
- **Deprecated kwargs in analysis utilities** — `beforeYAG_time`, `after_abs_time`, `end_time` are backward-compat aliases, not dead code
- **Inline function definitions in old Jupyter notebooks** — frozen analysis snapshots, not code duplication