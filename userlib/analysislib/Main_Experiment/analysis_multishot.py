"""Multi-shot analysis template for lyse.

This script runs after each shot and has access to the full DataFrame
of results accumulated by single-shot routines. Adapt the example
below to aggregate whichever results your single-shot analysis saves.
"""
import lyse
import numpy as np
import matplotlib.pyplot as plt

df = lyse.data()

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
