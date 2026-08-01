"""Compile connection_table.py outside RunManager/BLACS.

Usage (labscript conda env, from userlib/labscriptlib/Main_Experiment/):
    python tools/compile_ct.py                     # file's own ENABLED values
    python tools/compile_ct.py ni_6535=1 camera=1  # override switches for this run

Prints COMPILE OK + every device/channel name in the compiled connection
table. Exit 0 on success. Each run uses a fresh process and a throwaway h5,
so labscript's compiler state is always clean.
"""
import os
import sys
import tempfile

# userlib root (contains labscriptlib/ and user_devices/) must be importable,
# same as RunManager arranges via labconfig.
USERLIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, USERLIB)

import labscript  # noqa: E402  (imports labscript_utils.h5_lock before h5py)
import h5py  # noqa: E402
from labscript import start, stop  # noqa: E402

CT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'connection_table.py')
)


def main():
    overrides = {}
    for arg in sys.argv[1:]:
        key, sep, val = arg.partition('=')
        if not sep or val not in ('0', '1'):
            sys.exit(f"bad argument {arg!r} — expected switch=0 or switch=1")
        overrides[key] = bool(int(val))

    run_file = os.path.join(tempfile.mkdtemp(), 'ct_compile_check.h5')
    # runmanager-style run file: just needs a globals group
    with h5py.File(run_file, 'w') as f:
        f.create_group('globals')

    labscript.labscript_init(
        run_file, labscript_file=CT_PATH, load_globals_values=False
    )
    import labscriptlib.Main_Experiment.connection_table as ct_mod

    enabled = getattr(ct_mod, 'ENABLED', None)
    if overrides:
        if enabled is None:
            sys.exit("this connection_table.py has no ENABLED dict — no overrides possible")
        unknown = set(overrides) - set(enabled)
        if unknown:
            sys.exit(f"unknown switches: {sorted(unknown)} — valid: {sorted(enabled)}")
        enabled.update(overrides)

    ct_mod.connection_table()
    start()
    stop(1.0)
    labscript.labscript_cleanup()

    with h5py.File(run_file, 'r') as f:
        names = sorted(row['name'].decode() for row in f['connection table'][:])
    print('COMPILE OK — connection table rows:')
    for name in names:
        print('  ' + name)


if __name__ == '__main__':
    main()
