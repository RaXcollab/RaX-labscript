import labscript_utils.h5_lock
import h5py

from user_devices.RemoteControl.blacs_workers import RemoteControlWorker


class RasteringWorker(RemoteControlWorker):
    """
    Extends RemoteControlWorker with raster stepping support.

    When raster_mode is enabled (via tab checkbox), transition_to_buffered
    sends 'move_to_next' to advance the raster before the shot, then
    captures X/Y position into the HDF5 record.
    """

    def init(self):
        super().init()
        self.raster_mode = False

    def update_raster_mode(self, raster_mode):
        self.raster_mode = raster_mode

    def transition_to_buffered(self, device_name, h5_filepath, front_panel_values, fresh):
        if not self.enable_comms:
            return {}

        self.h5_filepath = h5_filepath

        # Step 1: Advance raster if enabled.
        if self.raster_mode:
            if not self.remote_comms.connected:
                raise Exception(
                    "Cannot advance raster: not connected to rastering GUI.\n"
                    "Check that the rastering GUI is running."
                )

            response = self.remote_comms.program_value(
                "move_to_next", 1, wait_for_lock=True
            )

            if response is None:
                raise Exception(
                    "Raster move_to_next timed out.\n"
                    "The rastering GUI may not be responding."
                )

            # v2 maps the legacy "FINISHED" pseudo-status to SUCCESS with
            # an extra `finished` field (spec §1.3 fixes the 5-token enum;
            # iterator-end is communicated as a SUCCESS reply variant).
            status = response.get("status", "")
            if status == "SUCCESS" and response.get("finished") is True:
                raise Exception(
                    "Raster sequence complete — no more points in the path.\n"
                    "Re-arm the raster in the rastering GUI to continue."
                )
            # Any non-SUCCESS status -> raise via the v2-aware checker
            # (handles ERROR/REJECTED/TIMEOUT/UNKNOWN_CONNECTION uniformly).
            self._check_response(response, "raster_move_to_next")

            self.logger.debug(f"Raster move_to_next: {response}")

        # Step 2: Program any explicit setpoints from HDF5 (if present)
        with h5py.File(h5_filepath, 'r') as f:
            group = f['devices'][self.device_name]
            if 'remote_device_operation' in group:
                if not self.remote_comms.connected:
                    raise Exception(
                        "Cannot program remote device: connection not established.\n"
                        "Please check connection and try again."
                    )
                table = group['remote_device_operation'][:]
                for connection in table.dtype.names:
                    value = float(table[0][connection])
                    self.logger.debug(
                        f"transition_to_buffered: programming {connection} = {value}"
                    )
                    response = self.remote_comms.program_value(
                        connection, value, wait_for_lock=True
                    )
                    self._check_response(
                        response, f"buffered_program({connection}={value})"
                    )

        # Step 3: Capture X/Y position snapshot for the shot record.
        # Use PUB-SUB cached values (populated by the base RemoteControlWorker's
        # drain thread). dict() copy is atomic under the GIL.
        self.initial_monitor_values = dict(self._pubsub_cache)
        self.logger.info(
            f"initial_monitor_values: "
            f"{len(self.initial_monitor_values)} channels"
        )

        return {}

