import os
import h5py
import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
 
# --- 1. Metadata Helper ---
def extract_metadata(group, prefix=''):
    meta = {}
    for key, val in group.attrs.items():
        if val in [None, "", b''] or (isinstance(val, bytes) and val == b''): continue
        clean_key = f"{prefix}{key}"
        if isinstance(val, bytes): val = val.decode('utf-8')
        if isinstance(val, np.ndarray):
            if val.ndim == 0: val = val.item()
            elif val.size == 1: val = val[0]
        meta[clean_key] = val
    for key in group.keys():
        if isinstance(group[key], h5py.Group):
            meta.update(extract_metadata(group[key], prefix=f"{key}."))
    return meta
 
# --- 2. The Worker (Dual Purpose) ---
def read_shot(args):
    """
    Reads a single shot.
    If 'get_time' is True, it also extracts the time axis from the first trace found.
    """
    filepath, trace_names, get_time = args
    filename = os.path.basename(filepath)
    result = {'filename': filename, 'valid': False, 'time_axis': None}
 
    try:
        with h5py.File(filepath, 'r') as f:
            if 'data/traces' not in f: return result
 
            # A. Metadata
            if 'globals' in f:
                result.update(extract_metadata(f['globals']))
 
            # B. Traces
            traces_v = {}
            for t_name in trace_names:
                path = f'data/traces/{t_name}'
                if path in f:
                    dset = f[path]
                    # Always read Voltage
                    traces_v[t_name] = dset['values'][:]
                    
                    # C. Conditional Time Axis Read (Only runs if requested)
                    if get_time and result['time_axis'] is None:
                        # Dynamically find the time column (usually index 0)
                        t_col = dset.dtype.names[0]
                        result['time_axis'] = dset[t_col][:]
 
            if traces_v:
                result['traces_v'] = traces_v
                result['valid'] = True
 
    except Exception:
        pass
    return result
 
# --- 3. Main Loader ---
def load_sequence(seq_num, folder_root, trace_names):
    seq_folder = os.path.join(folder_root, f'{seq_num:04d}')
    if not os.path.exists(seq_folder): return None, None
 
    files = sorted([f for f in os.listdir(seq_folder) if f.endswith('.h5')])
    if not files: return None, None
 
    # --- Task Creation ---
    # We pass 'True' for get_time ONLY to the first file (index 0)
    tasks = [
        (os.path.join(seq_folder, f), trace_names, (i == 0))
        for i, f in enumerate(files)
    ]
    
    # print(f"Seq {seq_num}: Loading {len(files)} shots...")
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(read_shot, tasks))
 
    # --- Assembly ---
    valid_results = [r for r in results if r['valid']]
    meta_rows = []
    v_buffer = {name: [] for name in trace_names}
    shared_time = None
 
    for res in valid_results:
        # Check if this result contains the "Golden" time axis
        if res['time_axis'] is not None:
            shared_time = res.pop('time_axis')
        else:
            res.pop('time_axis', None) # Clean up None values
 
        traces = res.pop('traces_v')
        meta_rows.append(res)
        
        for name in trace_names:
            v_buffer[name].append(traces.get(name, None))
 
    if shared_time is None:
        print("Error: Could not extract time axis from the first file.")
        return None, None
 
    # Finalize
    df = pd.DataFrame(meta_rows)
    df.dropna(axis=1, how='all', inplace=True)
    
    final_data = {}
    for name, v_list in v_buffer.items():
        clean_v = [v for v in v_list if v is not None and v.shape == shared_time.shape]
        if clean_v:
            final_data[name] = {'data': np.stack(clean_v), 'time': shared_time}
 
    print(f"Seq {seq_num}: Loaded {len(df)} shots.")
    return df, final_data