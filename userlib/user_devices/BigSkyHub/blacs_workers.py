import re
from collections import defaultdict

import labscript_utils.h5_lock  # noqa: F401 — required before h5py
import h5py

from user_devices.RemoteControl.blacs_workers import RemoteControlWorker

# Safe activation order for BigSky YAG commands within each laser.
# Lower number = sent first.  Commands not listed get priority 99 (sent last).
COMMAND_ORDER = {
    "stop":          0,  # ensure standby before mode changes
    "qswitch_mode":  1,  # mode change requires standby
    "lamp_mode":     2,  # mode change requires standby
    "voltage":       3,  # set voltage before activating
    "lamps":         4,  # activate flashlamps
    "shutter":       5,  # requires lamps active
    "qswitch":       6,  # requires lamps + shutter
    "warmup":        7,  # compound command, last
    "start_lasing":  8,  # compound command, last
}

# Regex to split "YAG_1_voltage" → ("YAG_1", "voltage")
_PREFIX_RE = re.compile(r'^(.+?_\d+)_(.+)$')


class BigSkyWorker(RemoteControlWorker):
    """RemoteControlWorker subclass that enforces safe command ordering.

    The BigSky YAG server rejects commands that violate safety interlocks
    (e.g. opening the shutter before lamps are active).  This worker groups
    HDF5-programmed channels by laser prefix and sends them in the order
    defined by ``COMMAND_ORDER``.
    """

    def transition_to_buffered(self, device_name, h5_filepath, front_panel_values, fresh):
        if not self.enable_comms:
            return {}

        with h5py.File(h5_filepath, 'r') as f:
            group = f['devices'][self.device_name]

            if 'remote_device_operation' not in group:
                return {}

            if not self.remote_comms.connected:
                raise Exception(
                    "Cannot program BigSky lasers: connection not established.\n"
                    "Please check that the BigSky GUI is running."
                )

            self.h5_filepath = h5_filepath
            table = group['remote_device_operation'][:]

            # Group columns by laser prefix (e.g. YAG_1, YAG_2)
            grouped = defaultdict(list)
            for col in table.dtype.names:
                m = _PREFIX_RE.match(col)
                if m:
                    laser_prefix = m.group(1)
                    suffix = m.group(2)
                    grouped[laser_prefix].append((suffix, col))
                else:
                    # Unrecognised column — send at the end
                    grouped["_unknown"].append((col, col))

            # Program each laser's channels in safe order
            for laser_prefix in sorted(grouped.keys()):
                commands = grouped[laser_prefix]
                commands.sort(key=lambda x: COMMAND_ORDER.get(x[0], 99))

                for suffix, col in commands:
                    value = float(table[0][col])
                    self.logger.debug(
                        f"transition_to_buffered: programming {col} = {value} "
                        f"(laser={laser_prefix}, order={COMMAND_ORDER.get(suffix, 99)})"
                    )
                    response = self.remote_comms.program_value(
                        col, value, wait_for_lock=True
                    )
                    self._check_response(
                        response, f"buffered_program({col}={value})"
                    )

            # Snapshot monitor values before shot
            self.initial_monitor_values = self.check_all_remote_values()

        return {}
