from scipy.signal import butter, sosfiltfilt, sosfreqz
from scipy.signal import savgol_filter
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

def process_trace(time_ms, signal, tYAG, beforeYAG_time=1.95, after_abs_time=10.0, end_time=15.0, filter_on=True):
    """
    Remove linear drift and baseline offset from a trace.

    Parameters
    ----------
    time_ms : 1D array
        Time axis in ms.
    signal : 1D array
        Raw voltage trace (single shot).
    tYAG : float
        YAG trigger time in ms.
    beforeYAG_time : float
        Upper bound of pre-YAG region for fitting (ms).
    after_abs_time : float
        Start of post-absorption region for fitting (ms).
    end_time : float
        End of post-absorption region for fitting (ms).
    filter_on : bool
        If True → remove linear drift + baseline.
        If False → return original signal.

    Returns
    -------
    corrected_signal : 1D array
    """

    if not filter_on:
        return signal.copy()

    # Convert times to indices
    trigger_index = np.searchsorted(time_ms, tYAG)
    before_idx = np.searchsorted(time_ms, beforeYAG_time)
    after_idx = np.searchsorted(time_ms, after_abs_time)
    end_idx = np.searchsorted(time_ms, end_time)

    # Build fitting region (pre-YAG + late-time region)
    fit_time = np.concatenate((time_ms[:before_idx],
                               time_ms[after_idx:end_idx]))
    fit_data = np.concatenate((signal[:before_idx],
                               signal[after_idx:end_idx]))

    if len(fit_time) < 5:
        # Not enough points to fit safely
        return signal.copy()

    # Initial guess
    slope_guess = (fit_data[-1] - fit_data[0]) / (fit_time[-1] - fit_time[0])
    intercept_guess = np.mean(fit_data)

    popt, _ = curve_fit(line_func,
                        fit_time,
                        fit_data,
                        p0=[slope_guess, intercept_guess])

    slope, intercept = popt

    # Remove linear trend
    flat_data = signal - line_func(time_ms, slope, intercept)

    # Remove DC offset (pre-trigger region)
    offset = np.mean(flat_data[:trigger_index])
    corrected_signal = flat_data - offset

    return corrected_signal