#####################################################################
#                                                                   #
# /NI_SCOPE/blacs_workers.py                                        #
#                                                                   #
# A driver for interfacing NI-SCOPE devices in labscript            #
#                                                                   #
# Last Revised Oct. 2025 (edge trigger on TRIG, start-trigger mode) #
#                                                                   #
#####################################################################

import numpy as np
import labscript_utils.h5_lock   # noqa: F401  (keeps h5py thread-safe under labscript)
import h5py
import niscope
from blacs.tab_base_classes import Worker
import labscript_utils.properties


class NI_SCOPEWorker(Worker):
    def init(self):
        # Create the NI-SCOPE session
        self.scope = niscope.Session(self.addr)

        mfg = self.scope.instrument_manufacturer
        model = self.scope.instrument_model
        revision = self.scope.instrument_firmware_revision
        print(f'[NI_SCOPE] Connected to {mfg} {model} (FW {revision})')

    # ---------- enum helpers ----------
    def _to_vertical_coupling_enum(self, s):
        """Map to niscope.VerticalCoupling (supports AC/DC/GND)."""
        if isinstance(s, niscope.VerticalCoupling):
            return s
        key = str(s).strip().upper()
        mapping = {
            'DC': niscope.VerticalCoupling.DC,
            'AC': niscope.VerticalCoupling.AC,
            'GND': niscope.VerticalCoupling.GND,
        }
        return mapping.get(key, niscope.VerticalCoupling.DC)

    # ---------- helpers ----------
    def _configure_horizontal(self):
        """Start-trigger style capture with `ref_position=0` (no pre-trigger samples)."""
        self.scope.configure_horizontal_timing(
            min_sample_rate=self.min_sample_rate,
            min_num_pts=self.min_num_pts,
            ref_position=0,      # percent of record before trigger; 0 = trigger at sample 0 (start-trigger)
            num_records=1,
            enforce_realtime=True
        )
        print(f'[NI_SCOPE] Horizontal: fs_min={self.min_sample_rate}, N_min={self.min_num_pts}, ref_pos=0%')

    def _normalize_trigger_source(self, src):
        """Return (src_norm, mode) where mode is 'analog', 'digital', or 'immediate'.

        Pure-Python logic extracted to user_devices.NI_SCOPE._helpers so it can be
        unit-tested without niscope. This wrapper preserves the [NI_SCOPE] log
        line for the production-trace use case (aliased trigger source) across
        ALL input types — str, bytes, bytearray, whitespace-padded — matching
        the pre-refactor behavior exactly.
        """
        from ._helpers import normalize_trigger_source
        norm, mode = normalize_trigger_source(src)
        # Build a display form that matches the pre-refactor 's' (decoded if
        # bytes, whitespace-stripped, case-preserved). Then log iff the helper
        # actually rewrote the input (alias collapse to TRIG).
        if isinstance(src, (bytes, bytearray)):
            s_disp = src.decode("utf-8", errors="ignore").strip()
        elif src in (None, ""):
            s_disp = ""
        else:
            s_disp = str(src).strip()
        if norm == "TRIG" and s_disp.upper() != "TRIG":
            print(f"[NI_SCOPE] Mapping trigger_source '{s_disp}' -> '{norm}'")
        return norm, mode

    def _configure_trigger(self):
        src_raw = getattr(self, 'trigger_source', None)
        trig_delay = float(getattr(self, 'trigger_delay', 0.0))

        trig_level = float(getattr(self, 'trigger_level', 1.0))
        trig_slope = getattr(self, 'trigger_slope', 'POSITIVE')
        trig_coupling = getattr(self, 'trigger_coupling', 'DC')

        slope_map = {
            'POSITIVE': niscope.TriggerSlope.POSITIVE,
            'NEGATIVE': niscope.TriggerSlope.NEGATIVE
        }
        coupling_map = {
            'DC': niscope.TriggerCoupling.DC,
            'AC': niscope.TriggerCoupling.AC,
        }
        slope_enum = slope_map.get(str(trig_slope).upper(), niscope.TriggerSlope.POSITIVE)
        coupling_enum = coupling_map.get(str(trig_coupling).upper(), niscope.TriggerCoupling.DC)

        src, mode = self._normalize_trigger_source(src_raw)

        if mode == 'immediate':
            print('[NI_SCOPE] Trigger: immediate (no external source)')
            self.scope.configure_trigger_immediate()
            return

        if mode == 'analog':
            print(f"[NI_SCOPE] Trigger: ANALOG EDGE on '{src}', level={trig_level}, "
                  f"slope={slope_enum.name}, coupling={coupling_enum.name}, delay={trig_delay}")
            self.scope.configure_trigger_edge(
                trigger_source=src,
                level=trig_level,
                slope=slope_enum,
                trigger_coupling=coupling_enum,
                holdoff=0.0,
                delay=trig_delay
            )
            return

        print(f"[NI_SCOPE] Trigger: DIGITAL on '{src}', delay={trig_delay}")
        self.scope.configure_trigger_digital(
            trigger_source=src,
            delay=trig_delay
        )

    def _configure_vertical(self):
        self.channel_count = self.scope.channel_count
        if len(self.vertical_range) != self.channel_count:
            print(
                f'[NI_SCOPE] ERROR: vertical_range length {len(self.vertical_range)} '
                f'does not match channel_count {self.channel_count}'
            )
            return self.abort()

        vc = getattr(self, 'vertical_coupling', 'DC')
        if isinstance(vc, (list, tuple)):
            if len(vc) != self.channel_count:
                print(f"[NI_SCOPE] ERROR: vertical_coupling length {len(vc)} "
                      f"does not match channel_count {self.channel_count}")
                return self.abort()
            couplings = [self._to_vertical_coupling_enum(x) for x in vc]
        else:
            couplings = [self._to_vertical_coupling_enum(vc)] * self.channel_count

        for i in range(self.channel_count):
            self.scope.channels[i].configure_vertical(
                range=self.vertical_range[i],
                coupling=couplings[i]
            )
        pretty = [c.name for c in couplings]
        print(f'[NI_SCOPE] Vertical: ranges={self.vertical_range}, couplings={pretty}, '
              f'channels={self.channel_count}')

    # ---------- BLACS transitions ----------
    def transition_to_buffered(self, device_name, h5file, front_panel_values, refresh):
        try:
            self.scope.abort()
        except Exception as e:
            print(f'[NI_SCOPE] abort() at enter buffered (ignored): {e}')

        self.h5file = h5file
        self.device_name = device_name

        with h5py.File(h5file, 'r') as hdf5_file:
            print('\n' + h5file)
            self.scope_params = labscript_utils.properties.get(
                hdf5_file, device_name, 'device_properties'
            )

        for k, v in self.scope_params.items():
            setattr(self, k, v)

        self.trigger_source   = getattr(self, 'trigger_source', 'TRIG')
        self.trigger_level    = float(getattr(self, 'trigger_level', 1.0))
        self.trigger_delay    = float(getattr(self, 'trigger_delay', 0.0))
        self.trigger_slope    = getattr(self, 'trigger_slope', 'POSITIVE')
        self.trigger_coupling = getattr(self, 'trigger_coupling', 'DC')
        self.vertical_coupling = getattr(self, 'vertical_coupling', 'DC')

        print(f"[NI_SCOPE] Props: source={self.trigger_source}, level={self.trigger_level}, "
              f"slope={self.trigger_slope}, coup={self.trigger_coupling}, "
              f"Vcoupling={self.vertical_coupling}, delay={self.trigger_delay}")

        try:
            self._configure_horizontal()
            self._configure_trigger()
            self._configure_vertical()
        except Exception as e:
            print(f"[NI_SCOPE] ERROR during configuration: {e}")
            try:
                self.scope.abort()
            except Exception as e2:
                print(f"[NI_SCOPE] abort() after config error: {e2}")
            raise

        print('[NI_SCOPE] Initiating acquisition…')
        self.scope.initiate()
        return {}

    def post_experiment(self):
        """Per-shot: fetch acquired waveforms and write to h5.

        Runs after every shot (between queued shots and at queue end).
        Defining this method lets BLACS skip the backwards-compatibility scan
        in device_base_class.py:778 that otherwise costs ~80 ms on the first
        shot of every sequence.
        """
        try:
            self.channel_count = self.scope.channel_count
            self.num_samps_actual = self.scope.horz_record_length
            self.samp_rate_actual = self.scope.horz_sample_rate
            print(f'[NI_SCOPE] Post-shot: fs={self.samp_rate_actual:.6g} Hz, N={self.num_samps_actual}')
        except Exception as e:
            print(f'[NI_SCOPE] Warning reading actual timing: {e}')

        # Determine which channels to save (default: all)
        channels_to_save = getattr(self, 'channels_to_save', None)
        if channels_to_save is None:
            channels_to_save = list(range(self.channel_count))

        # NaN-fill so unsaved channels are explicitly marked invalid
        data = np.full([self.channel_count, self.min_num_pts], np.nan)
        for i in channels_to_save:
            wfm = self.scope.channels[i].fetch(num_records=1)
            ns = min(len(wfm[0].samples), self.min_num_pts)
            print(f'[NI_SCOPE] Fetch: CH{wfm[0].channel}, rec {wfm[0].record}, '
                  f'samples={len(wfm[0].samples)} (saving {ns})')
            data[i, :ns] = wfm[0].samples[:ns]

        with h5py.File(self.h5file, 'r+') as hdf_file:
            grp = hdf_file.require_group('/data/traces')
            print('[NI_SCOPE] Saving traces…')
            if self.device_name in grp:
                del grp[self.device_name]
            dset = grp.create_dataset(self.device_name, data=data)
            # Write time metadata so analysis can reconstruct time axis from attrs
            dset.attrs['sample_rate'] = float(getattr(self, 'samp_rate_actual', self.min_sample_rate))
            dset.attrs['t0'] = 0.0
            dset.attrs['channels_saved'] = channels_to_save
        print(f'[NI_SCOPE] Fetch complete. Channels saved: {channels_to_save}')

        try:
            self.scope.abort()
        except Exception as e:
            print(f'[NI_SCOPE] abort() after fetch (ignored): {e}')

        return True

    def transition_to_manual(self):
        """Queue-end only: per-shot fetch already happened in post_experiment."""
        print('[NI_SCOPE] transition_to_manual: scope idle (data saved by post_experiment).')
        return True

    def program_manual(self, values):
        return values

    def abort(self):
        print('[NI_SCOPE] abort()')
        try:
            self.scope.abort()
            return True
        except Exception as e:
            print(f'[NI_SCOPE] abort() error: {e}')
            return False

    def abort_buffered(self):
        print('[NI_SCOPE] abort_buffered()')
        return self.abort()

    def abort_transition_to_buffered(self):
        print('[NI_SCOPE] abort_transition_to_buffered()')
        return self.abort()

    def shutdown(self):
        print('[NI_SCOPE] shutdown()')
        try:
            self.scope.abort()
        except Exception as e:
            print(f'[NI_SCOPE] abort() during shutdown (ignored): {e}')
        try:
            self.scope.close()
        except Exception as e:
            print(f'[NI_SCOPE] close() during shutdown (ignored): {e}')

