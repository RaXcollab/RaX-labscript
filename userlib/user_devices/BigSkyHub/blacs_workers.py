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

# Fire-and-forget command suffixes — no readable state to poll via CHECK_VALUE
_COMMAND_SUFFIXES = {'warmup', 'start_lasing', 'stop'}


class BigSkyWorker(RemoteControlWorker):
    """RemoteControlWorker subclass that enforces safe command ordering.

    The BigSky YAG server rejects commands that violate safety interlocks
    (e.g. opening the shutter before lamps are active).  This worker groups
    HDF5-programmed channels by laser prefix and sends them in the order
    defined by ``COMMAND_ORDER``.
    """

    def init(self):
        super().init()
        # Track last-sent values so program_manual only sends changes.
        # Prevents re-sending lamps=1 when only lamp_mode changed, which
        # would cause the mode change to be rejected (requires standby).
        self._last_sent_values = {}

    def check_remote_values(self):
        """Override to skip fire-and-forget command channels and handle unregistered lasers.

        Skips command channels (warmup, start_lasing, stop) which have no
        readable state.  Also gracefully skips connections for lasers not yet
        launched in the BigSky GUI (unknown connection errors).
        """
        if not self.remote_comms.connected:
            return None

        remote_values = {}
        for connection in self.child_output_connections:
            m = _PREFIX_RE.match(connection)
            if m and m.group(2) in _COMMAND_SUFFIXES:
                continue
            response = self.remote_comms.check_remote_value(connection)
            if response is None:
                self.logger.warning(f"check_remote_values: timeout for {connection}")
                return None
            if response.get("status") != "SUCCESS":
                msg = response.get("message", "")
                if "unknown connection" in msg:
                    self.logger.debug(
                        f"check_remote_values: skipping {connection} (not registered in GUI)"
                    )
                    continue
                if "laser disconnected" in msg:
                    self.logger.warning(
                        f"check_remote_values: skipping {connection} (laser disconnected)"
                    )
                    continue
                # Other errors: raise as usual
                self._check_response(response, f"check_remote_values({connection})")
            remote_values[connection] = float(response["value"])
        # Seed last-sent tracking so program_manual knows the remote state
        self._last_sent_values.update(remote_values)
        return remote_values

    def check_all_remote_values(self):
        """Override to skip command channels and handle unregistered lasers.

        Used for pre/post-shot monitor snapshots.  Iterates outputs + monitors.
        """
        if not self.remote_comms.connected:
            return {}

        remote_values = {}
        for connection in self.child_connections:
            m = _PREFIX_RE.match(connection)
            if m and m.group(2) in _COMMAND_SUFFIXES:
                continue
            response = self.remote_comms.check_remote_value(connection)
            if response is None:
                self.logger.warning(f"check_all_remote_values: timeout for {connection}")
                continue
            if response.get("status") != "SUCCESS":
                msg = response.get("message", "")
                if "unknown connection" in msg:
                    self.logger.debug(
                        f"check_all_remote_values: skipping {connection} (not registered in GUI)"
                    )
                    continue
                if "laser disconnected" in msg:
                    self.logger.warning(
                        f"check_all_remote_values: skipping {connection} (laser disconnected)"
                    )
                    continue
                self._check_response(response, f"check_all({connection})")
            remote_values[connection] = float(response["value"])
        return remote_values

    def program_manual(self, front_panel_values):
        """Override to skip command channels, handle unregistered lasers,
        and only send values that actually changed.

        Sending only changed values prevents re-activating the laser when
        the user only changed lamp_mode or qswitch_mode (mode changes
        require the laser to be in standby).
        """
        if not self.remote_comms.connected:
            return {}
        if not self._initial_fetch_done:
            return {}

        for connection in self.child_output_connections:
            m = _PREFIX_RE.match(connection)
            if m and m.group(2) in _COMMAND_SUFFIXES:
                continue
            value = front_panel_values[connection]
            # Only send if value actually changed from last known state
            if self._last_sent_values.get(connection) == value:
                continue
            response = self.remote_comms.program_value(
                connection, value, wait_for_lock=False
            )
            if response is None:
                self.logger.warning(f"program_manual: timeout for {connection}")
                continue
            if response.get("status") != "SUCCESS":
                msg = response.get("message", "")
                if "unknown connection" in msg:
                    self.logger.debug(
                        f"program_manual: skipping {connection} (not registered in GUI)"
                    )
                    continue
                if "laser disconnected" in msg:
                    self.logger.warning(
                        f"program_manual: skipping {connection} (laser disconnected)"
                    )
                    continue
                self._check_response(response, f"program_manual({connection}={value})")
            self._last_sent_values[connection] = value
        return {}

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
