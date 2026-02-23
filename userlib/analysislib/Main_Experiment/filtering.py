from scipy.signal import butter, sosfiltfilt, sosfreqz
from scipy.signal import savgol_filter
import warnings
import numpy as np
from scipy.optimize import curve_fit

def line_func(x, A, B):
    return A*x + B
def smooth(data,window=5,poly_order=3):
    '''Function for smoothing data. Currently uses Savitzky-Golay filter,
    which fits a window of data onto a polynomial of some order, and then
    uses the polynomial to estimate the value'''
    #window value must be odd
    if window % 2 == 0:
        window+=1
    smoothed_data = savgol_filter(data, window, poly_order)
    return smoothed_data

def butter_lowpass_filter(data, lowcut, fs, order=5):
    sos = butter_lowpass(lowcut, fs, order=order)
    y = sosfiltfilt(sos, data)
    return y

def butter_lowpass(lowcut, fs, order=5):
    nyq = 0.5 * fs
    low = lowcut / nyq
    sos = butter(order, low, analog=False, btype='lowpass', output='sos')
    return sos

def process_trace(time_ms, signal, tYAG_ms,
                  margin_ms=0.05, tail_ms=1.0,
                  slope_warn_threshold=0.01, filter_on=True,
                  beforeYAG_time=None, after_abs_time=None, end_time=None):
    """
    Remove linear drift and baseline offset from a trace.

    Fitting regions are determined automatically:
      - Before region: time_ms < tYAG_ms - margin_ms
      - After region:  time_ms > time_ms[-1] - tail_ms

    A slope check on the after-region residuals warns if the signal
    has not fully decayed (i.e., the late-time background is not flat).

    Parameters
    ----------
    time_ms : 1D array
        Time axis in ms.
    signal : 1D array
        Raw voltage trace (single shot).
    tYAG_ms : float
        YAG trigger time in ms.
    margin_ms : float
        Buffer before tYAG for the pre-YAG fitting region (ms).
    tail_ms : float
        Duration of the late-time tail used for fitting (ms).
    slope_warn_threshold : float
        If the slope of the after-region residuals (V/ms) exceeds this,
        print a warning that the signal may not have decayed.
    filter_on : bool
        If True -> remove linear drift + baseline.
        If False -> return original signal.
    beforeYAG_time : float, optional
        **Deprecated.** Old absolute time threshold for the pre-YAG region.
        Converted to ``margin_ms = tYAG_ms - beforeYAG_time``.
        Use ``margin_ms`` instead.
    after_abs_time : float, optional
        **Deprecated.** Old absolute start time for the after-signal region.
        Used together with ``end_time`` to compute ``tail_ms``.
        Use ``tail_ms`` instead.
    end_time : float, optional
        **Deprecated.** Old absolute end time for the after-signal region.
        Converted to ``tail_ms = end_time - after_abs_time``.
        Use ``tail_ms`` instead.

    Returns
    -------
    corrected_signal : 1D array
    """
    # Handle deprecated kwargs -- convert to current API
    if beforeYAG_time is not None:
        warnings.warn(
            "process_trace(): 'beforeYAG_time' is deprecated. "
            "Use 'margin_ms' instead (margin_ms = tYAG_ms - beforeYAG_time).",
            DeprecationWarning, stacklevel=2)
        margin_ms = tYAG_ms - beforeYAG_time

    if after_abs_time is not None and end_time is not None:
        warnings.warn(
            "process_trace(): 'after_abs_time' and 'end_time' are deprecated. "
            "Use 'tail_ms' instead (tail_ms = end_time - after_abs_time).",
            DeprecationWarning, stacklevel=2)
        tail_ms = end_time - after_abs_time
    elif after_abs_time is not None or end_time is not None:
        warnings.warn(
            "process_trace(): 'after_abs_time' and 'end_time' must both be "
            "provided to take effect. Ignoring partial deprecated kwargs.",
            DeprecationWarning, stacklevel=2)

    if not filter_on:
        return signal.copy()

    # Determine fitting regions automatically
    before_mask = time_ms < (tYAG_ms - margin_ms)
    after_mask = time_ms > (time_ms[-1] - tail_ms)

    fit_time = np.concatenate((time_ms[before_mask], time_ms[after_mask]))
    fit_data = np.concatenate((signal[before_mask], signal[after_mask]))

    if len(fit_time) < 5:
        return signal.copy()

    # Linear drift fit
    slope_guess = (fit_data[-1] - fit_data[0]) / (fit_time[-1] - fit_time[0])
    intercept_guess = np.mean(fit_data)

    popt, _ = curve_fit(line_func, fit_time, fit_data,
                        p0=[slope_guess, intercept_guess])
    slope, intercept = popt

    # Remove linear trend
    flat_data = signal - line_func(time_ms, slope, intercept)

    # Remove DC offset (pre-trigger baseline)
    trigger_index = np.searchsorted(time_ms, tYAG_ms)
    if trigger_index > 0:
        offset = np.mean(flat_data[:trigger_index])
    else:
        offset = 0.0
    corrected_signal = flat_data - offset

    # Slope check on the after-region residuals
    after_residuals = corrected_signal[after_mask]
    after_times = time_ms[after_mask]
    if len(after_times) >= 2:
        after_slope = (after_residuals[-1] - after_residuals[0]) / (after_times[-1] - after_times[0])
        if abs(after_slope) > slope_warn_threshold:
            print(f"  [process_trace] Warning: late-time slope = {after_slope:.4f} V/ms "
                  f"(threshold {slope_warn_threshold}). Signal may not have fully decayed.")

    return corrected_signal