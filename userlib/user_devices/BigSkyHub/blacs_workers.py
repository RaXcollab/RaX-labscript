import re
import time
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

# Channels controlled by Keep Warm — program_manual must not override these
_WARMUP_CONTROLLED_SUFFIXES = {'lamps', 'shutter', 'qswitch', 'lamp_mode', 'qswitch_mode'}

# Serial command delay — wait for BigSky to process stop before mode changes
_CMD_DELAY_S = 0.2


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
        # Keep Warm state per laser prefix — set by tab via update_keep_warm
        self._keep_warm = getattr(self, 'keep_warm_state', {})
        # Armed state tracking — prevents re-arming between queued shots
        self._is_armed = {}

    # ── Keep Warm lifecycle ────────────────────────────────────────────

    def update_keep_warm(self, prefix, state):
        """Called by the tab when the user toggles Keep Warm."""
        self._keep_warm[prefix] = state
        if not state:
            self._is_armed.pop(prefix, None)

    def enter_warmup(self, prefix):
        """Enter warmup: internal trigger, lamps on, shutter closed, qswitch off.

        Sends commands directly (not through program_manual) because:
        - Command ordering must be enforced (stop before mode change)
        - Fire-and-forget channels (stop) are skipped by program_manual
        """
        if not self.remote_comms.connected:
            raise Exception(f"Cannot enter warmup for {prefix}: not connected")

        self._keep_warm[prefix] = True
        self._is_armed.pop(prefix, None)

        # Step 1: Standby (clears lamps/shutter/qswitch on hardware)
        self._send_cmd(f"{prefix}_stop", 1.0, f"enter_warmup: stop {prefix}")
        time.sleep(_CMD_DELAY_S)

        # Step 2: Switch to internal lamp mode (requires standby)
        self._send_cmd(f"{prefix}_lamp_mode", 0.0, f"enter_warmup: lamp_mode=0")
        self._last_sent_values[f"{prefix}_lamp_mode"] = 0.0

        # Step 3: Activate lamps (fires internally)
        self._send_cmd(f"{prefix}_lamps", 1.0, f"enter_warmup: lamps=1")
        self._last_sent_values[f"{prefix}_lamps"] = 1.0

        # Update tracking for channels cleared by stop
        self._last_sent_values[f"{prefix}_shutter"] = 0.0
        self._last_sent_values[f"{prefix}_qswitch"] = 0.0

        self.logger.info(
            f"enter_warmup: {prefix} warming (internal trigger, lamps on, "
            f"shutter closed, qswitch off)"
        )

    def exit_warmup(self, prefix):
        """Exit warmup: go to standby."""
        if not self.remote_comms.connected:
            self.logger.warning(f"Cannot exit warmup for {prefix}: not connected")
            return

        self._keep_warm[prefix] = False
        self._is_armed.pop(prefix, None)

        self._send_cmd(f"{prefix}_stop", 1.0, f"exit_warmup: stop {prefix}")

        # Clear tracked state so next program_manual re-sends everything
        for suffix in _WARMUP_CONTROLLED_SUFFIXES | {'lamps'}:
            self._last_sent_values.pop(f"{prefix}_{suffix}", None)

        self.logger.info(f"exit_warmup: {prefix} in standby")

    def _arm_laser(self, prefix):
        """Arm laser for experiment: external trigger, lamps/shutter/qswitch on.

        Called by transition_to_buffered when _is_armed is False.
        Voltage persists through stop — no re-send needed.
        """
        self.logger.info(f"_arm_laser: arming {prefix} from warmup")

        # Step 1: Standby
        self._send_cmd(f"{prefix}_stop", 1.0, f"arm: stop {prefix}")
        time.sleep(_CMD_DELAY_S)

        # Step 2: External lamp mode (requires standby)
        self._send_cmd(f"{prefix}_lamp_mode", 1.0, f"arm: lamp_mode=1")
        # Safety: ensure Q-switch stays internal (always qsm0 in our setup)
        self._send_cmd(f"{prefix}_qswitch_mode", 0.0, f"arm: qswitch_mode=0 (safety)")

        # Step 3: Activate
        self._send_cmd(f"{prefix}_lamps", 1.0, f"arm: lamps=1")
        time.sleep(_CMD_DELAY_S)

        # Step 4: Open shutter, arm qswitch
        self._send_cmd(f"{prefix}_shutter", 1.0, f"arm: shutter=1")
        self._send_cmd(f"{prefix}_qswitch", 1.0, f"arm: qswitch=1")

        # Update tracking
        self._last_sent_values.update({
            f"{prefix}_lamp_mode": 1.0,
            f"{prefix}_qswitch_mode": 0.0,
            f"{prefix}_lamps": 1.0,
            f"{prefix}_shutter": 1.0,
            f"{prefix}_qswitch": 1.0,
        })

        self._is_armed[prefix] = True
        self.logger.info(
            f"_arm_laser: {prefix} armed (lamp external, QS internal, shutter open, qswitch on)"
        )

    def _restore_warmup(self, prefix):
        """Restore warmup after shot queue ends or abort.

        Wrapped in try/except — must not raise or it blocks other devices.
        """
        try:
            if not self.remote_comms.connected:
                self.logger.warning(
                    f"_restore_warmup: skipping {prefix} (not connected)"
                )
                return

            self.logger.info(f"_restore_warmup: restoring {prefix} to warmup")

            # Step 1: Standby
            self._send_cmd(f"{prefix}_stop", 1.0, f"restore: stop {prefix}")
            time.sleep(_CMD_DELAY_S)

            # Step 2: Switch to internal lamp mode
            self._send_cmd(f"{prefix}_lamp_mode", 0.0, f"restore: lamp_mode=0")

            # Step 3: Activate lamps (internal firing)
            self._send_cmd(f"{prefix}_lamps", 1.0, f"restore: lamps=1")

            # Update tracking
            self._last_sent_values.update({
                f"{prefix}_lamp_mode": 0.0,
                f"{prefix}_lamps": 1.0,
                f"{prefix}_shutter": 0.0,
                f"{prefix}_qswitch": 0.0,
            })

            self._is_armed[prefix] = False
            self.logger.info(f"_restore_warmup: {prefix} back in warmup")

        except Exception as e:
            self.logger.error(f"_restore_warmup: failed for {prefix}: {e}")
            self._is_armed[prefix] = False

    def _send_cmd(self, connection, value, context):
        """Send a single command to the BigSky GUI. Raises on failure."""
        response = self.remote_comms.program_value(
            connection, value, wait_for_lock=False
        )
        self._check_response(response, context)

    def send_action(self, prefix, action):
        """Send a fire-and-forget action (stop/warmup/start_lasing) from the tab.

        Handles timeouts and errors gracefully — logs warning instead of raising,
        since these are user-initiated manual actions (not shot-critical).
        """
        conn = f"{prefix}_{action}"
        self.logger.info(f"send_action: {conn}")
        response = self.remote_comms.program_value(conn, 1.0, wait_for_lock=False)
        if response is None:
            self.logger.warning(f"send_action: timeout for {conn} (GUI may be busy)")
            return
        if response.get("status") != "SUCCESS":
            msg = response.get("message", "")
            self.logger.warning(f"send_action: {conn} failed: {msg}")
            return

    # ── Overrides ──────────────────────────────────────────────────────

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
        only send changed values, and guard warmup-controlled channels.

        When Keep Warm is active for a laser prefix, only voltage changes
        are sent.  Lamps/shutter/qswitch/modes are managed by the warmup
        lifecycle and must not be overridden by program_device().
        """
        if not self.remote_comms.connected:
            return {}
        if not self._initial_fetch_done:
            return {}

        for connection in self.child_output_connections:
            m = _PREFIX_RE.match(connection)
            if not m:
                continue
            prefix, suffix = m.group(1), m.group(2)

            # Skip fire-and-forget command channels
            if suffix in _COMMAND_SUFFIXES:
                continue

            # Guard: skip warmup-controlled channels when Keep Warm is active
            if self._keep_warm.get(prefix) and suffix in _WARMUP_CONTROLLED_SUFFIXES:
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
                # No BigSky channels in this shot — still auto-arm if needed
                self._auto_arm_if_needed()
                self.initial_monitor_values = self.check_all_remote_values()
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
                    wait = getattr(self, 'wait_for_lock', False)
                    response = self.remote_comms.program_value(
                        col, value, wait_for_lock=wait
                    )
                    self._check_response(
                        response, f"buffered_program({col}={value})"
                    )
                    # Fix pre-existing staleness: track all sent values
                    self._last_sent_values[col] = value

            # Auto-arm keep-warm lasers after h5 programming
            self._auto_arm_if_needed()

            # Snapshot monitor values before shot
            self.initial_monitor_values = self.check_all_remote_values()

        return {}

    def _auto_arm_if_needed(self):
        """Arm any keep-warm lasers that aren't already armed.

        Uses two-tier check:
        1. If _is_armed flag is True, verify against hardware via CHECK_VALUE.
           If hardware matches, skip. If not, re-arm.
        2. If _is_armed flag is False, also check hardware — user may have
           manually armed from the GUI. If hardware shows armed, update flag
           and skip. Otherwise, arm.
        """
        for prefix, keep_warm in self._keep_warm.items():
            if not keep_warm:
                continue

            if self._is_armed.get(prefix):
                # Flag says armed — verify hardware agrees
                if self._verify_armed_state(prefix):
                    self.logger.debug(
                        f"_auto_arm_if_needed: {prefix} verified armed, skipping"
                    )
                    continue
                else:
                    self.logger.info(
                        f"_auto_arm_if_needed: {prefix} flag=armed but hardware "
                        f"disagrees, re-arming"
                    )
            else:
                # Flag says not armed — check if user armed from GUI
                if self._verify_armed_state(prefix):
                    self.logger.info(
                        f"_auto_arm_if_needed: {prefix} already armed externally, "
                        f"skipping"
                    )
                    self._is_armed[prefix] = True
                    continue

            self._arm_laser(prefix)

    def _verify_armed_state(self, prefix):
        """Check hardware state via CHECK_VALUE to confirm laser is armed.

        Returns True if lamp_mode=1, lamps=1, shutter=1, qswitch=1,
        qswitch_mode=0. Returns False if any check fails or mismatches.
        """
        expected = {
            f"{prefix}_lamp_mode": 1.0,
            f"{prefix}_lamps": 1.0,
            f"{prefix}_shutter": 1.0,
            f"{prefix}_qswitch": 1.0,
            f"{prefix}_qswitch_mode": 0.0,
        }
        for connection, expected_val in expected.items():
            response = self.remote_comms.check_remote_value(connection)
            if response is None:
                self.logger.warning(
                    f"_verify_armed_state: timeout checking {connection}"
                )
                return False
            if response.get("status") != "SUCCESS":
                msg = response.get("message", "")
                if "unknown connection" in msg or "laser disconnected" in msg:
                    self.logger.debug(
                        f"_verify_armed_state: {connection} unavailable ({msg})"
                    )
                    return False
                self.logger.warning(
                    f"_verify_armed_state: failed to check {connection}: {msg}"
                )
                return False
            actual = float(response["value"])
            if actual != expected_val:
                self.logger.info(
                    f"_verify_armed_state: {connection} = {actual}, "
                    f"expected {expected_val}"
                )
                return False
        return True

    def transition_to_manual(self):
        """Restore warmup state for keep-warm lasers after queue ends."""
        for prefix, keep_warm in self._keep_warm.items():
            if keep_warm:
                self._restore_warmup(prefix)
        return True

    def abort_transition_to_buffered(self):
        for prefix, keep_warm in self._keep_warm.items():
            if keep_warm:
                self._restore_warmup(prefix)
        self.initial_monitor_values = {}
        self.final_monitor_values = {}
        return True

    def abort_buffered(self):
        for prefix, keep_warm in self._keep_warm.items():
            if keep_warm:
                self._restore_warmup(prefix)
        self.initial_monitor_values = {}
        self.final_monitor_values = {}
        return True
