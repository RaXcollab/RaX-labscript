"""Multi-shot analysis template for lyse.

This script runs after each shot and has access to the full DataFrame
of results accumulated by single-shot routines. Adapt the example
below to aggregate whichever results your single-shot analysis saves.
"""
import lyse
import numpy as np
import matplotlib.pyplot as plt

df = lyse.data()

# Drop shots flagged as failed by single-shot analysis (e.g.
# analysis_opencell2.py's 'failed_shot' result -- see docs/shot-h5-layout.md
# for the failed_shot attr semantics). Matches on ANY column named
# 'failed_shot' regardless of which single-shot script's group it lives
# under, so this keeps working if the group name changes.
failed_cols = [c for c in df.columns if isinstance(c, tuple) and c[-1] == 'failed_shot']
if failed_cols:
    is_failed = df[failed_cols].fillna(False).any(axis=1)
    n_dropped = int(is_failed.sum())
    if n_dropped:
        print(f"Multishot: dropping {n_dropped}/{len(df)} shot(s) flagged failed_shot")
    df = df[~is_failed]

# Example: aggregate a named result saved by single-shot analysis
# Uncomment and replace 'my_result' with your actual result name.
#
# if ('analysis', 'my_result') in df.columns:
#     values = df[('analysis', 'my_result')].dropna()
#     n_shots = len(values)
#     plt.figure(figsize=(10, 4))
#     plt.plot(np.arange(n_shots), values.values)
#     plt.xlabel('Shot number', fontsize=14)
#     plt.ylabel('Result', fontsize=14)
#     plt.title('Multi-shot trend', fontsize=16)

print(f"Multishot: {len(df)} shots loaded")
