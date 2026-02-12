"""
NI_SCOPE.py
Utilities to read and plot PXIe-5922 (NI_SCOPE) traces from Lyse HDF5 files.

Main API:
- set_grid(on: bool): enable/disable grid on plots.
- plot_ni_scope_channels(h5_path, show=True): plot Ch0 and Ch1 on one figure.
- quick_tree(h5_path): inspect HDF5 structure (for debugging).
"""

from __future__ import annotations
import os, re, h5py
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, Any, Tuple, Optional

# ---------------- Global plot setting ----------------
_GRID_ON = True

def set_grid(on: bool = True):
    """Enable or disable grid lines for NI_SCOPE plots."""
    global _GRID_ON
    _GRID_ON = bool(on)
    print(f"Grid {'ON' if _GRID_ON else 'OFF'} for NI_SCOPE plots.")


# ---------------- Helper functions -------------------

def _attrs(ds: h5py.Dataset) -> Dict[str, Any]:
    try:
        return {k: (v.decode() if isinstance(v, (bytes, bytearray)) else v)
                for k, v in ds.attrs.items()}
    except Exception:
        return {}

def _time_from_attrs(attrs: Dict[str, Any], n: int) -> Tuple[np.ndarray, str]:
    """Generate time axis from dt/sample_rate attrs (ms if found)."""
    dt = None
    if "dt" in attrs:
        dt = float(attrs["dt"])
    elif "sample_rate" in attrs:
        sr = float(attrs["sample_rate"])
        if sr > 0:
            dt = 1.0 / sr
    t0 = float(attrs.get("t0", 0.0))
    if dt is None:
        return np.arange(n, dtype=float), "Sample #"
    t = t0 + np.arange(n) * dt
    return t * 1000.0, "Time (ms)"   # convert to ms

def _single_dataset(ds: h5py.Dataset) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, str]]:
    """Return (t, ch0, ch1, xlabel) if ds has both channels (2×N or N×2)."""
    arr = ds[()]
    if not (isinstance(arr, np.ndarray) and arr.ndim == 2 and 2 in arr.shape):
        return None
    vals = arr if arr.shape[0] == 2 else arr.T
    attrs = _attrs(ds)
    t, xlabel = _time_from_attrs(attrs, vals.shape[1])
    return t, vals[0], vals[1], xlabel

def _extract_time_value(ds: h5py.Dataset) -> Tuple[np.ndarray, np.ndarray]:
    """Return (t, y) from Nx2 or 1D dataset."""
    arr = ds[()]
    attrs = _attrs(ds)
    if isinstance(arr, np.ndarray) and arr.ndim == 2 and arr.shape[1] == 2:
        t, y = arr[:, 0], arr[:, 1]
        if (t[-1] - t[0]) < 10: t = t * 1000.0  # seconds→ms
        return t, y
    if arr.ndim == 1:
        y = np.asarray(arr)
        t, _ = _time_from_attrs(attrs, y.size)
        return t, y
    return np.arange(arr.size), np.ravel(arr)

def quick_tree(h5_path: str, max_rows: int = 3):
    """Print quick summary of HDF5 file contents."""
    with h5py.File(h5_path, "r") as f:
        def _visit(name, obj):
            kind = "DSET" if isinstance(obj, h5py.Dataset) else "GRP "
            shape = getattr(obj, "shape", "")
            print(f"{kind:4} /{name} {shape}")
            if isinstance(obj, h5py.Dataset):
                try:
                    data = obj[()]
                    if isinstance(data, np.ndarray):
                        print("     sample:", np.array(data[:max_rows]))
                except Exception:
                    pass
        f.visititems(_visit)


# ---------------- Main plotting function ----------------

def plot_ni_scope_channels(h5_path: str, show: bool = True) -> Dict[str, np.ndarray]:
    """Plot both NI_SCOPE channels on a single plot and return arrays."""
    if not os.path.exists(h5_path):
        raise FileNotFoundError(h5_path)

    with h5py.File(h5_path, "r") as h5:
        # --- Direct dataset with both channels ---
        for key in ["data/traces/NI_SCOPE", "data/traces/ni_scope", "data/NI_SCOPE", "NI_SCOPE"]:
            if key in h5 and isinstance(h5[key], h5py.Dataset):
                hit = _single_dataset(h5[key])
                if hit:
                    t, ch0, ch1, xlabel = hit
                    if show:
                        plt.figure(figsize=(8,4))
                        plt.plot(t, ch0, label="Ch0")
                        plt.plot(t, ch1, label="Ch1")
                        plt.xlabel(xlabel)
                        plt.ylabel("Voltage (V)")
                        plt.title("NI_SCOPE Ch0 & Ch1")
                        if _GRID_ON: plt.grid(True)
                        plt.legend()
                        plt.tight_layout()
                        plt.show()
                    return {"t0": t, "y0": ch0, "t1": t, "y1": ch1}

        # --- Group with Ch0/Ch1 datasets ---
        for gkey in ["data/traces/NI_SCOPE", "data/traces/ni_scope", "data/NI_SCOPE", "NI_SCOPE"]:
            if gkey in h5 and isinstance(h5[gkey], h5py.Group):
                grp = h5[gkey]
                ch0, ch1 = None, None
                for name, obj in grp.items():
                    if not isinstance(obj, h5py.Dataset): continue
                    if re.search(r"(ch0|channel0|\b0\b)", name.lower()):
                        ch0 = obj
                    elif re.search(r"(ch1|channel1|\b1\b)", name.lower()):
                        ch1 = obj
                if ch0 and ch1:
                    t0, y0 = _extract_time_value(ch0)
                    t1, y1 = _extract_time_value(ch1)
                    if show:
                        plt.figure(figsize=(8,4))
                        plt.plot(t0, y0, label="Ch0")
                        plt.plot(t1, y1, label="Ch1")
                        plt.xlabel("Time (ms)")
                        plt.ylabel("Voltage (V)")
                        plt.title("NI_SCOPE Ch0 & Ch1")
                        if _GRID_ON: plt.grid(True)
                        plt.legend()
                        plt.tight_layout()
                        plt.show()
                    return {"t0": t0, "y0": y0, "t1": t1, "y1": y1}

        raise KeyError("Could not find NI_SCOPE channels. Use quick_tree() to inspect file.")



def ensure_time_ms(t, y, fs_hz=1_000_000):
    """
    NI_SCOPE.py returns ms if it can infer dt/sample_rate, otherwise returns sample index.
    Detect sample-index and convert to ms using assumed fs.
    """
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)

    if t.ndim != 1 or y.ndim != 1 or t.size != y.size or t.size < 2:
        return t, y

    dt = float(np.median(np.diff(t)))
    # Sample-index heuristic: dt ~ 1 and huge endpoint
    if 0.9 <= dt <= 1.1 and t[-1] > 1000:
        t = t * (1.0 / fs_hz) * 1000.0  # samples -> ms

    return t, y


def load_ni_scope_sequences(folder_path_day, seq_list, shot_indices=None, ch=0, fs_hz=1_000_000):
    """
    Load NI_SCOPE into dict keyed by sequence.

    Parameters
    ----------
    shot_indices : array-like or None
        Specific shot indices to load (e.g. [0,2,5]).
        If None → load all shots.
    """

    seq_list = np.atleast_1d(seq_list).astype(int).ravel().tolist()

    if shot_indices is not None:
        shot_indices = np.atleast_1d(shot_indices).astype(int).ravel().tolist()

    scope_seq_data = {} 

    for seq in seq_list:
        seq_folder = os.path.join(folder_path_day, f"{seq:04d}")
        if not os.path.isdir(seq_folder):
            print(f"Warning: folder does not exist: {seq_folder}")
            continue

        files = sorted([f for f in os.listdir(seq_folder) if f.endswith(".h5")])
        if not files:
            print(f"Seq {seq}: no .h5 files found")
            continue

        # Determine which shots to load
        if shot_indices is None:
            selected_indices = np.arange(len(files))
        else:
            selected_indices = np.array(shot_indices, dtype=int)

        shots = []
        used_files = []
        time_ref_ms = None

        skip_counts = {"read_error": 0, "bad_shape": 0,
                       "time_mismatch": 0, "index_out_of_range": 0, "ok": 0}

        for shot_idx in selected_indices:

            # Skip invalid indices
            if shot_idx < 0 or shot_idx >= len(files):
                skip_counts["index_out_of_range"] += 1
                continue

            h5_path = os.path.join(seq_folder, files[shot_idx])

            try:
                out = plot_ni_scope_channels(h5_path, show=False)
            except Exception as e:
                skip_counts["read_error"] += 1
                continue

            if ch == 0:
                t, y = out["t0"], out["y0"]
            else:
                t, y = out["t1"], out["y1"]

            t_ms, y = ensure_time_ms(t, y, fs_hz=fs_hz)

            if t_ms.ndim != 1 or y.ndim != 1 or t_ms.size != y.size:
                skip_counts["bad_shape"] += 1
                continue

            if time_ref_ms is None:
                time_ref_ms = t_ms
            else:
                if t_ms.size != time_ref_ms.size or not np.allclose(t_ms, time_ref_ms, rtol=0, atol=1e-12):
                    skip_counts["time_mismatch"] += 1
                    continue

            shots.append(y.astype(float))
            used_files.append(files[shot_idx])
            skip_counts["ok"] += 1

        if len(shots) == 0:
            print(f"Seq {seq}: no valid shots | skip_counts={skip_counts}")
            continue

        scope_seq_data[seq] = {
            "scope_time_ms": time_ref_ms,
            "scope_values": np.stack(shots),
            "shot_files": used_files,
            "skip_counts": skip_counts
        }

        print(f"Seq {seq}: loaded {len(shots)} shots | skip_counts={skip_counts}")

    return scope_seq_data



# CLI for standalone use
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("h5_path", help="Path to Lyse HDF5 file")
    parser.add_argument("--no-show", action="store_true", help="Skip showing plots")
    parser.add_argument("--grid", type=int, default=1, help="1=grid on, 0=off")
    args = parser.parse_args()
    set_grid(bool(args.grid))
    plot_ni_scope_channels(args.h5_path, show=not args.no_show)
