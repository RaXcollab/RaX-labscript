"""
ScanAnalysis — load, process, and plot closed-cell scan data.

Usage:
    from scan_plots import ScanAnalysis
    sa = ScanAnalysis('path/to/0006', scan_col='TISA_1', secondary_col='V_YAG1')
    sa.spectroscopy()
    sa.time_traces(xlim=(-1, 10))
    sa.heatmap(t_range=(-1, 10))
"""

import os
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

from scan_analysis import load_scan_globals, load_scan_traces, load_scan_scope, integrate_window
from filtering import line_func


class ScanAnalysis:
    """Closed-cell scan analysis: OD + fluorescence."""

    def __init__(self, seq_folder, scan_col, secondary_col,
                 shutter_col='LIF_SHUTTER_OPEN',
                 abs_trace='Absorption3', scope_ch=0,
                 skip_first=True, scope_offset_ms=0):
        """Load and process a scan sequence.

        Parameters
        ----------
        seq_folder : str
            Path to the sequence folder (e.g. '.../0006').
        scan_col : str
            Global that is the primary scan variable (x-axis).
        secondary_col : str
            Global that gives separate curves/panels.
        shutter_col : str
            Boolean global for shutter interleaving.
        abs_trace : str
            Absorption trace name in h5.
        scope_ch : int
            NI_SCOPE channel index.
        skip_first : bool
            If True (default), drop the first shot (run_number 0). The first
            shot after BLACS starts is often bad due to hardware settling.
        scope_offset_ms : float
            Manual time offset for scope data (ms). If the fluorescence signal
            appears shifted relative to absorption, set this to align them.
            Positive values shift scope time forward (later in experiment time).
        """
        self.seq_folder = seq_folder
        self.scan_col = scan_col
        self.secondary_col = secondary_col
        self.shutter_col = shutter_col

        # Load ALL globals from h5 (every parameter the sequence used)
        self.df = load_scan_globals(seq_folder)

        # Drop first shot if requested
        if skip_first and len(self.df) > 1:
            first_idx = self.df.index[0]
            self.df = self.df.iloc[1:].reset_index(drop=True)
            print(f"Skipped first shot (run_number {first_idx})")

        self.tYAG_ms = float(self.df['tYAG'].iloc[0]) * 1000
        self.tstart_ms = float(self.df['tstart'].iloc[0]) * 1000
        self._scan_vals_raw = sorted(self.df[scan_col].unique())  # original units (for df lookups)
        self.sec_vals = sorted(self.df[secondary_col].unique())

        # Convert THz frequencies to MHz offset from minimum value.
        # Detection: values > 100 with sub-GHz span (ptp < 0.01 THz).
        sv = np.array(self._scan_vals_raw)
        if len(sv) > 1 and np.min(sv) > 100 and np.ptp(sv) < 0.01:
            self.scan_ref_THz = np.min(sv)
            self.scan_vals = (sv - self.scan_ref_THz) * 1e6  # MHz array
            self.scan_label = f'{scan_col} - {self.scan_ref_THz:.6f} THz [MHz]'
        else:
            self.scan_ref_THz = None
            self.scan_vals = sv  # keep original units
            self.scan_label = scan_col

        # Load traces
        abs_data = load_scan_traces(seq_folder, abs_trace, df=self.df)
        self.abs_time_ms = abs_data['time'] * 1000
        self._abs_raw = abs_data['data']

        scope_data = load_scan_scope(seq_folder, ch=scope_ch, df=self.df)

        # Auto-correct scope pre-trigger offset.
        # The NI_SCOPE records with ref_position=1% (hardcoded in driver),
        # meaning 1% of the record is pre-trigger data. The scope triggers
        # off the daq_ao0 BNC pulse at tstart. So scope_time=0 is actually
        # (pre_trigger_ms) before tstart in experiment time.
        # We subtract the pre-trigger duration to align with experiment time.
        if scope_offset_ms == 0:
            n_pts = scope_data['time_ms'].shape[0]
            fs = n_pts / (scope_data['time_ms'][-1] / 1000) if scope_data['time_ms'][-1] > 0 else 1e6
            ref_position_pct = 1.0  # hardcoded in NI_SCOPE driver
            pre_trigger_ms = ref_position_pct / 100 * n_pts / fs * 1000
            scope_offset_ms = -pre_trigger_ms
            print(f"Scope pre-trigger correction: {pre_trigger_ms:.1f} ms "
                  f"({ref_position_pct}% of {n_pts} pts @ {fs/1e6:.1f} MHz)")

        self.scope_time_ms = scope_data['time_ms'] + scope_offset_ms

        # Process
        self.abs_OD = self._compute_od()
        self.scope_corrected = self._baseline_scope(scope_data['data'])

        # Integration bounds (set by interactive_bounds, used by spectroscopy)
        self.abs_int = None  # (start, end) in ms relative to tYAG
        self.fl_int = None

        self._print_summary()

    # ---- processing ----

    def _compute_od(self):
        """Drift-correct then Beer-Lambert OD."""
        t = self.abs_time_ms
        trig = np.searchsorted(t, self.tYAG_ms)
        before = t < (self.tYAG_ms - 0.05)
        after = t > (t[-1] - 5.0)

        od = np.zeros_like(self._abs_raw)
        for i in range(self._abs_raw.shape[0]):
            raw = self._abs_raw[i]
            if np.all(np.isnan(raw)):
                continue
            fit_t = np.concatenate((t[before], t[after]))
            fit_v = np.concatenate((raw[before], raw[after]))
            if len(fit_t) < 5:
                continue
            popt, _ = curve_fit(line_func, fit_t, fit_v, p0=[0, np.mean(fit_v)])
            detrended = raw - popt[0] * t
            I0 = np.mean(detrended[:trig])
            with np.errstate(divide='ignore', invalid='ignore'):
                row = -np.log(detrended / I0)
            od[i] = np.where(np.isfinite(row), row, 0.0)
        return od

    def _baseline_scope(self, data):
        """Pre-YAG baseline subtraction for scope."""
        idx = np.searchsorted(self.scope_time_ms, self.tYAG_ms)
        baseline = np.nanmean(data[:, :idx], axis=1, keepdims=True)
        return data - baseline

    def _print_summary(self):
        trig = np.searchsorted(self.abs_time_ms, self.tYAG_ms)
        print(f"ScanAnalysis loaded: {len(self.df)} shots")
        print(f"  {self.scan_col}: {len(self._scan_vals_raw)} values")
        print(f"  {self.secondary_col}: {self.sec_vals}")
        print(f"  tYAG = {self.tYAG_ms} ms")
        print(f"  OD range (post-YAG): {np.nanmin(self.abs_OD[:, trig:]):.4f} "
              f"to {np.nanmax(self.abs_OD[:, trig:]):.4f}")
        # Fluorescence peak timing (helps user set scope_offset_ms)
        sc_trig = np.searchsorted(self.scope_time_ms, self.tYAG_ms)
        avg_fl = np.nanmean(np.abs(self.scope_corrected), axis=0)
        peak_idx = np.argmax(avg_fl[sc_trig:]) + sc_trig
        fl_peak_ms = self.scope_time_ms[peak_idx]
        print(f"  Fluorescence peak at {fl_peak_ms:.2f} ms "
              f"(tYAG={self.tYAG_ms:.1f}, offset={fl_peak_ms - self.tYAG_ms:.2f} ms)")

    # ---- helpers ----

    def _to_raw_scan(self, scan_val):
        """Convert a scan value (MHz or raw) back to original units for df lookup."""
        if self.scan_ref_THz is not None:
            return scan_val / 1e6 + self.scan_ref_THz
        return scan_val

    def _get_indices(self, scan_val_raw, sec_val, shutter=None):
        """Get df indices matching the given globals. scan_val_raw must be in original units."""
        mask = (self.df[self.scan_col] == scan_val_raw) & \
               (self.df[self.secondary_col] == sec_val)
        if shutter is not None:
            mask = mask & (self.df[self.shutter_col] == shutter)
        return self.df.index[mask].tolist()

    @staticmethod
    def _avg_integrate(traces_2d, time_ms, t_start, t_end, err_list, sign=1):
        """Average traces, integrate, propagate std through the integral.

        Appends the propagated error to err_list and returns the integrated mean.
        sigma_integral = sqrt(sum(sigma_i^2)) * dt, where sigma_i is the
        per-timepoint std across shots.
        """
        idx0 = np.searchsorted(time_ms, t_start)
        idx1 = np.searchsorted(time_ms, t_end)
        if idx1 <= idx0:
            err_list.append(0)
            return 0.0
        dt = np.median(np.diff(time_ms[idx0:idx1]))
        mean_trace = np.mean(traces_2d, axis=0)
        val = sign * np.trapz(mean_trace[idx0:idx1], dx=dt)
        if traces_2d.shape[0] > 1:
            std_trace = np.std(traces_2d[:, idx0:idx1], axis=0)
            sigma = np.sqrt(np.sum(std_trace**2)) * dt
            err_list.append(sigma)
        else:
            err_list.append(0)
        return val

    # ---- plots ----

    def spectroscopy(self, int_start=0.05, int_end=30.0,
                     abs_int=None, fl_int=None,
                     secondary_filter=None, mode='shot', figsize=(18, 5)):
        """Integrated signal vs scan variable.

        Each point integrates the OD or fluorescence trace over a time window
        after the YAG trigger, then plots the result vs the scan variable.

        Parameters
        ----------
        int_start, int_end : float
            Default integration window (offsets from tYAG in ms). Used for both
            absorption and fluorescence unless overridden by abs_int / fl_int.
        abs_int : tuple (start, end), optional
            Absorption-specific integration window (offsets from tYAG in ms).
            Overrides int_start/int_end for absorption only.
        fl_int : tuple (start, end), optional
            Fluorescence-specific integration window (offsets from tYAG in ms).
            Overrides int_start/int_end for fluorescence only.
        secondary_filter : list, optional
            Show only these secondary values. e.g. [870] to plot only V_YAG1=870.
        mode : str, 'shot' or 'avg'
            How to handle multiple shots at the same scan point:
            - 'shot': integrate each shot separately, plot mean +/- std as error
              bars. Use this to assess shot-to-shot reproducibility.
            - 'avg': average the time series across shots first, then integrate
              once. Error bars are propagated from the per-timepoint std
              through the integral: sigma = sqrt(sum(sigma_i^2)) * dt.
              Better SNR than 'shot' mode; use for the cleanest spectroscopy.
        figsize : tuple
            Figure size (width, height) in inches.
        """
        # Resolution: explicit kwargs > stored bounds > int_start/int_end defaults
        if abs_int is None and self.abs_int is not None:
            abs_int = self.abs_int
        if fl_int is None and self.fl_int is not None:
            fl_int = self.fl_int
        a_s = self.tYAG_ms + (abs_int[0] if abs_int else int_start)
        a_e = self.tYAG_ms + (abs_int[1] if abs_int else int_end)
        f_s = self.tYAG_ms + (fl_int[0] if fl_int else int_start)
        f_e = self.tYAG_ms + (fl_int[1] if fl_int else int_end)
        print(f"Bounds: abs=({a_s - self.tYAG_ms:.2f}, {a_e - self.tYAG_ms:.1f}), "
              f"fl=({f_s - self.tYAG_ms:.2f}, {f_e - self.tYAG_ms:.1f}) ms from tYAG")
        svs = secondary_filter or self.sec_vals

        fig, (ax_ao, ax_ac, ax_fl) = plt.subplots(1, 3, figsize=figsize)

        for sv in svs:
            xd = []  # x-values in MHz (or raw units)
            ao, ao_err, ac, ac_err = [], [], [], []
            fo, fo_err, fc, fc_err = [], [], [], []
            for xi, xv in enumerate(self._scan_vals_raw):
                oi = self._get_indices(xv, sv, shutter=True)
                ci = self._get_indices(xv, sv, shutter=False)
                if not oi:
                    continue
                xd.append(self.scan_vals[xi])

                if mode == 'shot':
                    ao_s = integrate_window(self.abs_time_ms, self.abs_OD[oi], a_s, a_e)
                    fo_s = -integrate_window(self.scope_time_ms, self.scope_corrected[oi], f_s, f_e)
                    ao.append(np.mean(ao_s)); ao_err.append(np.std(ao_s) if len(ao_s) > 1 else 0)
                    fo.append(np.mean(fo_s)); fo_err.append(np.std(fo_s) if len(fo_s) > 1 else 0)
                    if ci:
                        ac_s = integrate_window(self.abs_time_ms, self.abs_OD[ci], a_s, a_e)
                        fc_s = -integrate_window(self.scope_time_ms, self.scope_corrected[ci], f_s, f_e)
                        ac.append(np.mean(ac_s)); ac_err.append(np.std(ac_s) if len(ac_s) > 1 else 0)
                        fc.append(np.mean(fc_s)); fc_err.append(np.std(fc_s) if len(fc_s) > 1 else 0)
                    else:
                        ac.append(np.nan); ac_err.append(0)
                        fc.append(np.nan); fc_err.append(0)
                else:  # mode == 'avg'
                    ao.append(self._avg_integrate(self.abs_OD[oi], self.abs_time_ms, a_s, a_e, ao_err))
                    fo.append(self._avg_integrate(self.scope_corrected[oi], self.scope_time_ms, f_s, f_e, fo_err, sign=-1))
                    if ci:
                        ac.append(self._avg_integrate(self.abs_OD[ci], self.abs_time_ms, a_s, a_e, ac_err))
                        fc.append(self._avg_integrate(self.scope_corrected[ci], self.scope_time_ms, f_s, f_e, fc_err, sign=-1))
                    else:
                        ac.append(np.nan); ac_err.append(0)
                        fc.append(np.nan); fc_err.append(0)

            # Both modes use errorbar (avg mode has propagated errors)
            ax_ao.errorbar(xd, ao, yerr=ao_err, fmt='o-', label=f'{sv}', markersize=4, capsize=2)
            ax_ac.errorbar(xd, ac, yerr=ac_err, fmt='o-', label=f'{sv}', markersize=4, capsize=2)
            ax_fl.errorbar(xd, fo, yerr=fo_err, fmt='o-', label=f'{sv} open', markersize=4, capsize=2)
            ax_fl.errorbar(xd, fc, yerr=fc_err, fmt='s--', label=f'{sv} closed', markersize=4, capsize=2, alpha=0.7)

        for ax, title in [(ax_ao, 'Absorption OD (shutter open)'),
                          (ax_ac, 'Absorption OD (shutter closed)'),
                          (ax_fl, 'Fluorescence: open vs closed')]:
            ax.set_xlabel(self.scan_label)
            ax.set_title(title)
            ax.legend(title=self.secondary_col, fontsize=8)
            ax.grid(True, alpha=0.3)
        ax_ao.set_ylabel('Integrated OD [ms]')
        ax_ac.set_ylabel('Integrated OD [ms]')
        ax_fl.set_ylabel('Integrated fluorescence [V·ms]')
        plt.tight_layout()
        plt.show()
        # Use plt.gcf() to capture figures if needed

    def time_traces(self, xlim=(-1, 10), secondary_filter=None, figsize=(14, 5)):
        """Averaged time traces per secondary value, shutter open vs closed.

        Parameters
        ----------
        xlim : tuple
            (start, end) in ms relative to tYAG.
        secondary_filter : list, optional
            Subset of secondary values to plot.
        """
        svs = secondary_filter or self.sec_vals
        colors = [f'C{i}' for i in range(len(svs))]
        t_abs = self.abs_time_ms - self.tYAG_ms
        t_fl = self.scope_time_ms - self.tYAG_ms

        fig_a, (ax_ao, ax_ac) = plt.subplots(1, 2, figsize=figsize)
        fig_f, (ax_fo, ax_fc) = plt.subplots(1, 2, figsize=figsize)

        for ci, sv in enumerate(svs):
            ao, ac, fo, fc = [], [], [], []
            for xv in self._scan_vals_raw:
                oi = self._get_indices(xv, sv, shutter=True)
                cii = self._get_indices(xv, sv, shutter=False)
                if oi:
                    ao.append(np.mean(self.abs_OD[oi], axis=0))
                    fo.append(np.mean(self.scope_corrected[oi], axis=0))
                if cii:
                    ac.append(np.mean(self.abs_OD[cii], axis=0))
                    fc.append(np.mean(self.scope_corrected[cii], axis=0))

            for traces, ax, t in [(ao, ax_ao, t_abs), (ac, ax_ac, t_abs),
                                   (fo, ax_fo, t_fl), (fc, ax_fc, t_fl)]:
                if not traces:
                    continue
                stack = np.array(traces)
                sign = -1 if ax in (ax_fo, ax_fc) else 1
                for tr in stack:
                    ax.plot(t, sign * tr, color=colors[ci], alpha=0.1, linewidth=0.5)
                ax.plot(t, sign * np.mean(stack, axis=0),
                        color=colors[ci], lw=1.5, label=f'{sv}')

        for ax, title in [(ax_ao, 'Absorption OD (shutter open)'),
                          (ax_ac, 'Absorption OD (shutter closed)')]:
            ax.axvline(0, color='r', ls='--', alpha=0.5, label='YAG')
            ax.set_xlim(*xlim)
            ax.set_xlabel('Time relative to YAG [ms]')
            ax.set_ylabel('OD')
            ax.set_title(title)
            ax.legend(title=self.secondary_col)
            ax.grid(True, alpha=0.3)

        for ax, title in [(ax_fo, 'Fluorescence (shutter open)'),
                          (ax_fc, 'Fluorescence (shutter closed)')]:
            ax.axvline(0, color='r', ls='--', alpha=0.5, label='YAG')
            ax.set_xlim(*xlim)
            ax.set_xlabel('Time relative to YAG [ms]')
            ax.set_ylabel('-Voltage [V]')
            ax.set_title(title)
            ax.legend(title=self.secondary_col)
            ax.grid(True, alpha=0.3)

        fig_a.suptitle('Absorption OD time traces')
        fig_a.tight_layout()
        fig_f.suptitle('Fluorescence time traces')
        fig_f.tight_layout()
        plt.show()
        # Use plt.gcf() to capture figures if needed

    def heatmap(self, t_range=(-1, 10), shutter='open',
                secondary_filter=None, figsize_per_panel=(5, 5)):
        """2D heatmap: time vs scan variable.

        Parameters
        ----------
        t_range : tuple
            (start, end) in ms relative to tYAG.
        shutter : str
            'open', 'closed', or 'both'.
        secondary_filter : list, optional
            Subset of secondary values to plot.
        figsize_per_panel : tuple
            (width, height) per panel.
        """
        svs = secondary_filter or self.sec_vals
        nsv = len(svs)
        shutter_bool = True if shutter == 'open' else (False if shutter == 'closed' else None)

        # Time crops
        abs_t = self.abs_time_ms - self.tYAG_ms
        abs_mask = (abs_t >= t_range[0]) & (abs_t <= t_range[1])
        abs_crop = abs_t[abs_mask]

        sc_t = self.scope_time_ms - self.tYAG_ms
        sc_mask = (sc_t >= t_range[0]) & (sc_t <= t_range[1])
        sc_crop = sc_t[sc_mask]

        scan_arr = np.array(self.scan_vals)  # MHz or raw units
        n_scan = len(scan_arr)

        abs_hm, fl_hm = {}, {}
        for sv in svs:
            a2d = np.full((abs_mask.sum(), n_scan), np.nan)
            f2d = np.full((sc_mask.sum(), n_scan), np.nan)
            for si, xv in enumerate(self._scan_vals_raw):
                idxs = self._get_indices(xv, sv, shutter=shutter_bool)
                if idxs:
                    a2d[:, si] = np.mean(self.abs_OD[idxs], axis=0)[abs_mask]
                    f2d[:, si] = -np.mean(self.scope_corrected[idxs], axis=0)[sc_mask]
            abs_hm[sv] = a2d
            fl_hm[sv] = f2d

        abs_vmax = max(np.nanmax(np.abs(h)) for h in abs_hm.values())
        fl_vmax = max(np.nanmax(np.abs(h)) for h in fl_hm.values())

        w = figsize_per_panel[0] * nsv + 2
        h = figsize_per_panel[1]

        # Absorption
        fig_a, ax_a = plt.subplots(1, nsv, figsize=(w, h),
                                    sharey=True, constrained_layout=True)
        if nsv == 1:
            ax_a = [ax_a]
        for i, sv in enumerate(svs):
            pcm = ax_a[i].pcolormesh(scan_arr, abs_crop, abs_hm[sv],
                                      shading='nearest', cmap='RdBu_r',
                                      vmin=-abs_vmax, vmax=abs_vmax)
            ax_a[i].axhline(0, color='k', ls='--', lw=0.8, alpha=0.6)
            ax_a[i].set_xlabel(self.scan_label)
            ax_a[i].set_title(f'{self.secondary_col} = {sv}')
            if i == 0:
                ax_a[i].set_ylabel('Time relative to YAG [ms]')
        fig_a.colorbar(pcm, ax=ax_a, shrink=0.8, pad=0.02, label='OD')
        fig_a.suptitle(f'Absorption OD (shutter {shutter})')
        plt.show()

        # Fluorescence
        fig_f, ax_f = plt.subplots(1, nsv, figsize=(w, h),
                                    sharey=True, constrained_layout=True)
        if nsv == 1:
            ax_f = [ax_f]
        for i, sv in enumerate(svs):
            pcm = ax_f[i].pcolormesh(scan_arr, sc_crop, fl_hm[sv],
                                      shading='nearest', cmap='inferno',
                                      vmin=0, vmax=fl_vmax)
            ax_f[i].axhline(0, color='w', ls='--', lw=0.8, alpha=0.6)
            ax_f[i].set_xlabel(self.scan_label)
            ax_f[i].set_title(f'{self.secondary_col} = {sv}')
            if i == 0:
                ax_f[i].set_ylabel('Time relative to YAG [ms]')
        fig_f.colorbar(pcm, ax=ax_f, shrink=0.8, pad=0.02, label='-Voltage [V]')
        fig_f.suptitle(f'Fluorescence (shutter {shutter})')
        plt.show()
        # Use plt.gcf() to capture figures if needed

    def single_trace(self, scan_val, sec_val, shutter=True, figsize=(12, 4)):
        """Plot individual shot traces for a specific (scan_val, sec_val) point.

        scan_val should be in the same units as self.scan_vals (MHz if frequency).
        Useful for inspecting raw data quality.
        """
        idxs = self._get_indices(self._to_raw_scan(scan_val), sec_val, shutter=shutter)
        if not idxs:
            print(f"No shots found for {self.scan_col}={scan_val}, "
                  f"{self.secondary_col}={sec_val}, shutter={shutter}")
            return

        fig, (ax_a, ax_f) = plt.subplots(1, 2, figsize=figsize)
        t_abs = self.abs_time_ms - self.tYAG_ms
        t_fl = self.scope_time_ms - self.tYAG_ms

        for i in idxs:
            ax_a.plot(t_abs, self.abs_OD[i], alpha=0.5, linewidth=0.8)
            ax_f.plot(t_fl, -self.scope_corrected[i], alpha=0.5, linewidth=0.8)

        for ax, title, ylabel in [(ax_a, 'Absorption OD', 'OD'),
                                   (ax_f, 'Fluorescence', '-Voltage [V]')]:
            ax.axvline(0, color='r', ls='--', alpha=0.5)
            ax.set_xlim(-1, 10)
            ax.set_xlabel('Time relative to YAG [ms]')
            ax.set_ylabel(ylabel)
            ax.set_title(f'{title} — {self.scan_col}={scan_val}, '
                         f'{self.secondary_col}={sec_val}')
            ax.grid(True, alpha=0.3)

        shutter_str = 'open' if shutter else 'closed'
        fig.suptitle(f'{len(idxs)} shots (shutter {shutter_str})', fontsize=12)
        fig.tight_layout()
        plt.show()
        # Use plt.gcf() to capture figures if needed

    def overview(self, xlim=(-1, 15), shutter='open', figsize=(14, 5)):
        """Plot ALL traces overlaid to visualize signal range and pick integration bounds.

        Shows every shot's OD and fluorescence trace in light color, with the
        global mean on top. Use this to decide int_start / int_end before
        running spectroscopy().

        Parameters
        ----------
        xlim : tuple
            Time window relative to tYAG (ms).
        shutter : str
            'open' or 'closed' — which shutter state to show.
        figsize : tuple
            Figure size.
        """
        shutter_bool = shutter == 'open'
        mask = self.df[self.shutter_col] == shutter_bool
        idxs = self.df.index[mask].tolist()
        if not idxs:
            print(f"No shots with shutter={shutter}")
            return

        t_abs = self.abs_time_ms - self.tYAG_ms
        t_fl = self.scope_time_ms - self.tYAG_ms

        fig, (ax_a, ax_f) = plt.subplots(1, 2, figsize=figsize)

        # Plot every trace at low alpha
        for i in idxs:
            ax_a.plot(t_abs, self.abs_OD[i], color='C0', alpha=0.15, linewidth=0.5)
            ax_f.plot(t_fl, -self.scope_corrected[i], color='C1', alpha=0.15, linewidth=0.5)

        # Mean trace
        ax_a.plot(t_abs, np.mean(self.abs_OD[idxs], axis=0),
                  color='C0', linewidth=1.5, label='mean')
        ax_f.plot(t_fl, -np.mean(self.scope_corrected[idxs], axis=0),
                  color='C1', linewidth=1.5, label='mean')

        for ax, title, ylabel in [(ax_a, 'Absorption OD', 'OD'),
                                   (ax_f, 'Fluorescence', '-Voltage [V]')]:
            ax.axvline(0, color='r', ls='--', alpha=0.5, label='YAG')
            ax.set_xlim(*xlim)
            ax.set_xlabel('Time relative to YAG [ms]')
            ax.set_ylabel(ylabel)
            ax.set_title(title)
            ax.legend(loc='upper right')
            ax.grid(True, alpha=0.3)

        fig.suptitle(f'All {len(idxs)} traces (shutter {shutter}) — '
                     f'use to pick integration bounds', fontsize=12)
        fig.tight_layout()
        plt.show()

    def interactive_bounds(self, shutter='open', xlim=(-1, 30)):
        """Interactive integration window picker with click-drag, sliders, and text boxes.

        Three ways to set bounds (all stay synced):
        1. Click-drag on the plot to select a region (requires %matplotlib widget)
        2. Adjust sliders for coarse control
        3. Type exact values in text boxes

        Bounds are stored on ``self.abs_int`` and ``self.fl_int`` and automatically
        used by ``spectroscopy()`` when called without explicit bounds.

        Parameters
        ----------
        shutter : str
            'open' or 'closed' — which shutter state to show.
        xlim : tuple
            Default x-axis range (ms relative to tYAG). With %matplotlib widget
            you can also pan/zoom interactively.
        """
        import ipywidgets as widgets
        from IPython.display import display
        import matplotlib
        from matplotlib.widgets import SpanSelector

        shutter_bool = shutter == 'open'
        mask = self.df[self.shutter_col] == shutter_bool
        idxs = self.df.index[mask].tolist()

        t_abs = self.abs_time_ms - self.tYAG_ms
        t_fl = self.scope_time_ms - self.tYAG_ms
        mean_od = np.mean(self.abs_OD[idxs], axis=0)
        mean_fl = -np.mean(self.scope_corrected[idxs], axis=0)

        # Check if we have an interactive backend for SpanSelector
        backend = matplotlib.get_backend().lower()
        has_interactive = 'widget' in backend or 'nbagg' in backend

        # ---- Build synced widgets ----
        style = {'description_width': '80px'}
        sl_layout = widgets.Layout(width='280px')
        tx_layout = widgets.Layout(width='90px')

        # Initial values: use stored bounds if available, else defaults
        a_s0 = self.abs_int[0] if self.abs_int else 0.05
        a_e0 = self.abs_int[1] if self.abs_int else 10.0
        f_s0 = self.fl_int[0] if self.fl_int else 0.05
        f_e0 = self.fl_int[1] if self.fl_int else 10.0

        w_abs_s = widgets.FloatSlider(value=a_s0, min=-1, max=50, step=0.05,
                                       description='Start:', style=style,
                                       layout=sl_layout, continuous_update=False)
        t_abs_s = widgets.FloatText(value=a_s0, layout=tx_layout, step=0.05)
        w_abs_e = widgets.FloatSlider(value=a_e0, min=0, max=50, step=0.1,
                                       description='End:', style=style,
                                       layout=sl_layout, continuous_update=False)
        t_abs_e = widgets.FloatText(value=a_e0, layout=tx_layout, step=0.1)
        w_fl_s = widgets.FloatSlider(value=f_s0, min=-1, max=50, step=0.05,
                                      description='Start:', style=style,
                                      layout=sl_layout, continuous_update=False)
        t_fl_s = widgets.FloatText(value=f_s0, layout=tx_layout, step=0.05)
        w_fl_e = widgets.FloatSlider(value=f_e0, min=0, max=50, step=0.1,
                                      description='End:', style=style,
                                      layout=sl_layout, continuous_update=False)
        t_fl_e = widgets.FloatText(value=f_e0, layout=tx_layout, step=0.1)

        # Toggle: mean-only vs spread (all traces overlaid)
        w_spread = widgets.Checkbox(value=True, description='Show all traces',
                                    style={'description_width': 'auto'},
                                    layout=widgets.Layout(width='180px'))

        # Link slider <-> text bidirectionally
        widgets.link((w_abs_s, 'value'), (t_abs_s, 'value'))
        widgets.link((w_abs_e, 'value'), (t_abs_e, 'value'))
        widgets.link((w_fl_s, 'value'), (t_fl_s, 'value'))
        widgets.link((w_fl_e, 'value'), (t_fl_e, 'value'))

        # ---- Shared state for plot elements ----
        _patches = {'abs': None, 'fl': None}
        _spread_lines = {'abs': [], 'fl': []}  # individual trace line artists
        _updating = [False]
        sa_self = self

        def _store_bounds():
            sa_self.abs_int = (round(w_abs_s.value, 3), round(w_abs_e.value, 3))
            sa_self.fl_int = (round(w_fl_s.value, 3), round(w_fl_e.value, 3))

        def _update_patches(fig):
            ax_a, ax_f = fig.axes[0], fig.axes[1]
            for key, ax, ws, we in [('abs', ax_a, w_abs_s, w_abs_e),
                                     ('fl', ax_f, w_fl_s, w_fl_e)]:
                if _patches[key] is not None:
                    _patches[key].remove()
                _patches[key] = ax.axvspan(ws.value, we.value,
                                           alpha=0.15, color='green')
            ax_a.set_title(f'Absorption — abs_int=({w_abs_s.value:.2f}, {w_abs_e.value:.1f})')
            ax_f.set_title(f'Fluorescence — fl_int=({w_fl_s.value:.2f}, {w_fl_e.value:.1f})')
            fig.canvas.draw_idle()

        # Subsample traces if too many (plotting 200+ lines kills performance)
        _MAX_SPREAD = 60
        if len(idxs) > _MAX_SPREAD:
            _spread_idxs = sorted(np.random.default_rng(0).choice(
                idxs, _MAX_SPREAD, replace=False))
        else:
            _spread_idxs = idxs

        def _toggle_spread(fig):
            """Show/hide individual trace lines."""
            show = w_spread.value
            ax_a, ax_f = fig.axes[0], fig.axes[1]
            # Lazy-create spread lines on first toggle
            if not _spread_lines['abs'] and show:
                for i in _spread_idxs:
                    ln, = ax_a.plot(t_abs, self.abs_OD[i], color='C0',
                                    alpha=0.12, linewidth=0.5, rasterized=True)
                    _spread_lines['abs'].append(ln)
                    ln2, = ax_f.plot(t_fl, -self.scope_corrected[i], color='C1',
                                     alpha=0.12, linewidth=0.5, rasterized=True)
                    _spread_lines['fl'].append(ln2)
            for ln in _spread_lines['abs'] + _spread_lines['fl']:
                ln.set_visible(show)
            fig.canvas.draw_idle()

        # ---- Create figure ----
        # Performance: increase path simplification for many overlaid traces
        import matplotlib as _mpl
        _mpl.rcParams['path.simplify_threshold'] = 0.5

        if has_interactive:
            fig, (ax_a, ax_f) = plt.subplots(1, 2, figsize=(14, 4))
            fig.canvas.toolbar_visible = True
            fig.canvas.header_visible = False

            # Mean traces (always visible, on top)
            ax_a.plot(t_abs, mean_od, 'C0', lw=1.5, zorder=10, label='mean')
            ax_f.plot(t_fl, mean_fl, 'C1', lw=1.5, zorder=10, label='mean')

            for ax in (ax_a, ax_f):
                ax.axvline(0, color='r', ls='--', alpha=0.5, label='YAG')
                ax.set_xlim(*xlim)
                ax.set_xlabel('Time relative to YAG [ms]')
                ax.grid(True, alpha=0.3)
                ax.legend(loc='upper right', fontsize=8)
            ax_a.set_ylabel('OD')
            ax_f.set_ylabel('-Voltage [V]')

            _update_patches(fig)
            _toggle_spread(fig)  # show spread by default
            fig.tight_layout()

            # SpanSelector for click-drag
            def _on_abs_select(xmin, xmax):
                if _updating[0]:
                    return
                _updating[0] = True
                w_abs_s.value = round(xmin, 3)
                w_abs_e.value = round(xmax, 3)
                _store_bounds()
                _update_patches(fig)
                _updating[0] = False

            def _on_fl_select(xmin, xmax):
                if _updating[0]:
                    return
                _updating[0] = True
                w_fl_s.value = round(xmin, 3)
                w_fl_e.value = round(xmax, 3)
                _store_bounds()
                _update_patches(fig)
                _updating[0] = False

            span_props = dict(alpha=0.3, facecolor='green')
            _span_abs = SpanSelector(ax_a, _on_abs_select, 'horizontal',
                                     useblit=True, props=span_props,
                                     interactive=True, drag_from_anywhere=True)
            _span_fl = SpanSelector(ax_f, _on_fl_select, 'horizontal',
                                    useblit=True, props=span_props,
                                    interactive=True, drag_from_anywhere=True)
            fig._span_selectors = (_span_abs, _span_fl)

            plt.show()

            # "Set Bounds" applies slider/text values to the plot
            def _apply_bounds_interactive(b=None):
                _updating[0] = True
                _store_bounds()
                _update_patches(fig)
                _toggle_spread(fig)
                _updating[0] = False

            _apply_bounds_fn = _apply_bounds_interactive
        else:
            # Inline backend: full redraw on apply (no SpanSelector)
            out = widgets.Output()

            def _apply_bounds_inline(b=None):
                _store_bounds()
                with out:
                    out.clear_output(wait=True)
                    fig2, (ax_a2, ax_f2) = plt.subplots(1, 2, figsize=(14, 4))
                    if w_spread.value:
                        for i in _spread_idxs:
                            ax_a2.plot(t_abs, self.abs_OD[i], color='C0',
                                       alpha=0.12, linewidth=0.5, rasterized=True)
                            ax_f2.plot(t_fl, -self.scope_corrected[i], color='C1',
                                       alpha=0.12, linewidth=0.5, rasterized=True)
                    ax_a2.plot(t_abs, mean_od, 'C0', lw=1.5, label='mean')
                    ax_f2.plot(t_fl, mean_fl, 'C1', lw=1.5, label='mean')
                    ax_a2.axvspan(w_abs_s.value, w_abs_e.value, alpha=0.15, color='green')
                    ax_f2.axvspan(w_fl_s.value, w_fl_e.value, alpha=0.15, color='green')
                    ax_a2.set_title(f'Absorption — abs_int=({w_abs_s.value:.2f}, {w_abs_e.value:.1f})')
                    ax_f2.set_title(f'Fluorescence — fl_int=({w_fl_s.value:.2f}, {w_fl_e.value:.1f})')
                    for ax in (ax_a2, ax_f2):
                        ax.axvline(0, color='r', ls='--', alpha=0.5)
                        ax.set_xlim(*xlim)
                        ax.set_xlabel('Time relative to YAG [ms]')
                        ax.grid(True, alpha=0.3)
                        ax.legend(loc='upper right', fontsize=8)
                    ax_a2.set_ylabel('OD')
                    ax_f2.set_ylabel('-Voltage [V]')
                    fig2.tight_layout()
                    plt.show()

            _apply_bounds_fn = _apply_bounds_inline

        # ---- Buttons ----
        btn_set = widgets.Button(description='Set Bounds',
                                 button_style='info',
                                 layout=widgets.Layout(width='140px'))
        btn_set.on_click(_apply_bounds_fn)

        spec_out = widgets.Output()
        btn_spec = widgets.Button(description='Run Spectroscopy',
                                  button_style='success',
                                  layout=widgets.Layout(width='200px'))

        def _on_run_spec(b):
            _apply_bounds_fn()  # apply current slider values first
            with spec_out:
                spec_out.clear_output(wait=True)
                sa_self.spectroscopy()

        btn_spec.on_click(_on_run_spec)

        # Store initial bounds
        _store_bounds()

        # ---- Layout: controls grouped per channel ----
        abs_controls = widgets.VBox([
            widgets.HTML('<b>Absorption bounds (ms from tYAG)</b>'),
            widgets.HBox([w_abs_s, t_abs_s]),
            widgets.HBox([w_abs_e, t_abs_e]),
        ])
        fl_controls = widgets.VBox([
            widgets.HTML('<b>Fluorescence bounds (ms from tYAG)</b>'),
            widgets.HBox([w_fl_s, t_fl_s]),
            widgets.HBox([w_fl_e, t_fl_e]),
        ])
        control_row = widgets.HBox([abs_controls, fl_controls],
                                   layout=widgets.Layout(gap='40px'))
        bottom_row = widgets.HBox([w_spread, btn_set, btn_spec],
                                  layout=widgets.Layout(gap='20px'))

        if has_interactive:
            display(control_row)
            # figure already shown by plt.show()
        else:
            display(widgets.VBox([control_row, out]))
            _apply_bounds_fn()

        display(bottom_row, spec_out)

        n_traces = len(idxs)
        spread_note = (f" (showing {_MAX_SPREAD}/{n_traces} for speed)"
                       if len(idxs) > _MAX_SPREAD else "")
        print(f"{n_traces} shots loaded{spread_note}. "
              f"Adjust sliders/text, then click Set Bounds. "
              f"Or drag on plot to select.")
        if not has_interactive:
            print("Tip: Use %matplotlib widget before this cell for click-drag support.")
