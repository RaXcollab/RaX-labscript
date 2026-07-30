---
name: h5-inspect
description: Dump a shot h5 file's structure (groups, datasets, root attrs) and the authoritative remote_device_operation scan values via h5py, read-only — in-session replacement for opening HDFView. Blank argument = newest shot.
argument-hint: "[path-to-shot.h5 | blank = latest shot]"
---

Inspect a BLACS shot file without leaving the session. Opens the file **read-only**
(`h5py.File(path, "r")` — shot files are also written by BLACS/lyse; never open `r+`).
Shot storage layout is `<Experiment>\YYYY\MM\DD\<seq#>\*.h5` (experiment folder first).

## Inspect

```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python - "$ARGUMENTS" <<'PY'
import os, sys, glob, datetime
import h5py

ROOT = r"C:\Users\radmo\MIT Dropbox\Shungo Fukaya\Experiments\Main_Experiment"

arg = sys.argv[1].strip().strip('"') if len(sys.argv) > 1 else ""
if arg:
    path = arg
    if not os.path.isfile(path):
        print(f"ERROR: file not found: {path}")
        sys.exit(1)
else:
    # layout: <Experiment>/YYYY/MM/DD/<seq#>/*.h5
    candidates = glob.glob(os.path.join(ROOT, "*", "*", "*", "*", "*", "*.h5"))
    if not candidates:
        print(f"ERROR: no .h5 shots found under {ROOT}")
        sys.exit(1)
    def safe_mtime(p):  # a candidate can vanish between glob and stat (Dropbox sync)
        try:
            return os.path.getmtime(p)
        except OSError:
            return 0.0
    path = max(candidates, key=safe_mtime)

st = os.stat(path)
print(f"FILE  {path}")
print(f"      {st.st_size/1e6:.2f} MB   mtime {datetime.datetime.fromtimestamp(st.st_mtime):%Y-%m-%d %H:%M:%S}")

def fmt_value(ds):
    try:
        return repr(ds[()])
    except Exception as e:  # ponytail: unreadable dataset shouldn't kill the dump
        return f"<unreadable: {e}>"

try:
    with h5py.File(path, "r") as f:
        print("\n== ROOT ATTRS ==")
        for k, v in f.attrs.items():
            print(f"  {k} = {v!r}")

        print("\n== TREE ==")
        def show(name, obj):
            if isinstance(obj, h5py.Dataset):
                line = f"  {name}  shape={obj.shape} dtype={obj.dtype}"
                if obj.size is not None and obj.size <= 10:
                    line += f"  value={fmt_value(obj)}"
                print(line)
            else:
                print(f"  {name}/")
        f.visititems(show)

        print("\n== SCAN VALUES (/devices/*/remote_device_operation - authoritative x-axis) ==")
        found = False
        for dev, grp in f.get("devices", {}).items():
            if not isinstance(grp, h5py.Group) or "remote_device_operation" not in grp:
                continue
            found = True
            rdo = grp["remote_device_operation"]
            print(f"  {dev}:")
            if isinstance(rdo, h5py.Dataset):
                if rdo.dtype.names:
                    val = rdo[()]
                    for ch in rdo.dtype.names:
                        print(f"    {ch} = {val[ch]!r}")
                else:
                    print(f"    {fmt_value(rdo)}")
            else:
                for ch, ds in rdo.items():
                    print(f"    {ch} = {fmt_value(ds)}")
        if not found:
            print("  (none)")
except OSError as e:
    print(f"ERROR: cannot open {path}: {e}")
    sys.exit(1)
PY
```

## Report

Summarize: the file identity line, the device list found under `/devices/`, and any
`remote_device_operation` scan channels/values (these are the authoritative scan
x-axis — full float64 labscript intent). Relay the full tree only if the user asked
for structure; otherwise keep it to the summary. The file was opened read-only.

If a path argument was given, confirm the printed `FILE` line matches the requested
path; if it doesn't (argument substitution failed), re-run the block with the literal
path in place of `$ARGUMENTS`. An `unable to lock file` error means the shot is still
being written by BLACS/lyse — retry after the shot completes; do NOT pass
`locking=False` (risks reading torn data).
