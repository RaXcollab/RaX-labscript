The NI_SCOPE device (`userlib/user_devices/NI_SCOPE/`) is a custom NI-5922 high-speed digitizer driver. Data flows: connection table params → h5 properties → worker → h5 dataset + attrs → analysis.

**h5 dataset layout:** `/data/traces/NI_SCOPE` — shape `[channel_count, N]` (always 2D, even with selective saving). Channel index = row index.

**Dataset attributes (written by worker):**
- `sample_rate` — actual sample rate in Hz (from `scope.horz_sample_rate` post-acquisition)
- `t0` — time offset in seconds (currently 0.0; reserved for future trigger delay support)
- `channels_saved` — list of channel indices that contain real data (e.g., `[0, 1]` or `[0]`)

**Selective channel saving:** `channels_to_save` in the connection table controls which channels are fetched. Unsaved channels are NaN-filled (preserves array shape for backward compat). Analysis code should check `channels_saved` attr or test for NaN.

**Sample rate resolution in analysis (`_resolve_fs_hz`):** Fallback chain:
1. Dataset attrs `sample_rate` (new files)
2. Connection table property `min_sample_rate`
3. User-provided `fs_hz` kwarg
4. Default 1 MHz

**NaN-padding pattern:** When optional data columns exist, fill with NaN rather than omitting. This preserves indexing semantics (`channel 0 = row 0`) and makes missing data visible (NaN propagates) rather than silent.
