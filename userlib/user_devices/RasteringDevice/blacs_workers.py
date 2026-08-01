import labscript_utils.h5_lock
import h5py

from user_devices.RemoteControl.blacs_workers import RemoteControlWorker


class RasteringWorker(RemoteControlWorker):
    """
    Extends RemoteControlWorker with raster stepping support.

    When raster_mode is enabled (via tab checkbox), transition_to_buffered
    advances the raster before the shot — arming the raster on the GUI
    (in step mode) if it isn't armed yet, then sending 'move_to_next' on
    the first shot of each group of ``shots_per_step`` shots — and
    captures X/Y position into the HDF5 record.

    Control changes are also pushed to the GUI immediately
    (``_sync_raster_mode_to_gui``): ticking the checkbox arms the GUI then
    and there instead of at the first shot, and unticking it disarms.
    That eager path never raises — the lazy arm in ``_advance_raster``
    remains the backstop, and only per-shot failures fail a shot.
    """

    def init(self):
        super().init()
        self._init_raster_state()

    def _init_raster_state(self):
        # raster_mode / shots_per_step arrive as workerargs (the tab
        # forwards the restored checkbox + spinbox state), already set
        # as instance attributes before init() runs — normalize, don't
        # clobber.
        self.raster_mode = bool(getattr(self, "raster_mode", False))
        self.shots_per_step = max(1, int(getattr(self, "shots_per_step", 1)))
        self._shots_since_step = 0
        self._raster_armed = False
        # Last N the GUI acknowledged; None means "the GUI doesn't know N".
        self._last_synced_shots_per_step = None

    def connect_to_remote(self):
        """Connect, then push the current raster controls to the GUI.

        A fresh connection may be a restarted GUI, so anything we believed
        about its armed state is void. Syncing here is what makes a
        restored-checked checkbox arm the GUI at BLACS startup rather than
        at the first shot.
        """
        connected = super().connect_to_remote()
        if connected:
            self._raster_armed = False
            self._last_synced_shots_per_step = None
            self._sync_raster_mode_to_gui()
        return connected

    def update_raster_mode(self, raster_mode, shots_per_step=1):
        """Settings change: restart the group count and re-sync the GUI now."""
        was_enabled = self.raster_mode
        self.raster_mode = bool(raster_mode)
        self.shots_per_step = max(1, int(shots_per_step))
        self._shots_since_step = 0
        # _raster_armed is deliberately NOT cleared here: an N change must
        # only resend N. Clearing it would re-arm — harmless on a live raster
        # (the server's already-armed branch just re-modes) but if the GUI
        # raster was meanwhile stopped/finished, an arm-from-scratch would
        # silently restart the path from point 1 as a side effect of a
        # spinbox nudge. Keeping the flag means that case instead fails
        # loudly at the next shot (raster_not_active -> heal -> re-arm).
        # The disable branch of the sync clears it.
        self._sync_raster_mode_to_gui(was_enabled=was_enabled)

    def _send_shots_per_step(self):
        """Tell the GUI how many shots we take per point (it displays N).

        Returns True if the GUI acknowledged. Never raises: BLACS owns the
        stepping decision, so failing to sync N is cosmetic and must not
        fail a shot or red-error the tab.
        """
        try:
            response = self.remote_comms.program_value(
                "shots_per_step", self.shots_per_step
            )
            self._check_response(response, "raster_shots_per_step")
        except Exception as e:
            self.logger.warning(
                f"Could not sync shots_per_step={self.shots_per_step} to the "
                f"rastering GUI: {e}"
            )
            return False
        self._last_synced_shots_per_step = self.shots_per_step
        return True

    def _sync_raster_mode_to_gui(self, was_enabled=None):
        """Arm/disarm the GUI and push N as soon as the controls change.

        NEVER raises — toggling the checkbox with the GUI closed must not put
        the BLACS tab into an error state. On an arm failure the armed flag
        is left False so ``_advance_raster``'s lazy arm stays the backstop
        (and that path still raises, failing the shot loudly).
        """
        if not self.remote_comms.connected:
            self.logger.info(
                "Raster mode change not pushed to the rastering GUI: not "
                "connected. It will be applied on reconnect, or by the lazy "
                "arm on the first stepped shot."
            )
            return

        if self.raster_mode:
            if not self._raster_armed:
                try:
                    response = self.remote_comms.program_value(
                        "arm_raster", 0, wait_for_lock=True
                    )
                    self._check_response(response, "raster_arm(settings)")
                except Exception as e:
                    self.logger.warning(
                        f"Could not arm the rastering GUI now: {e}. The next "
                        f"stepped shot will retry (and fail loudly if it "
                        f"still can't arm)."
                    )
                    return
                self._raster_armed = True
                self._last_synced_shots_per_step = None  # fresh raster: resend N
            if self._last_synced_shots_per_step != self.shots_per_step:
                self._send_shots_per_step()
            return

        # Disabled: disarm only if the GUI might be armed on our behalf. A
        # spinbox jiggle with the box unchecked must not touch the GUI.
        if was_enabled or self._raster_armed:
            try:
                response = self.remote_comms.program_value("disarm_raster", 1)
                self._check_response(response, "raster_disarm")
            except Exception as e:
                # Includes raster_in_continuous_mode: a continuous raster
                # belongs to the GUI operator, not to us. Warn, never fail.
                self.logger.warning(f"Could not disarm the rastering GUI: {e}")
        self._raster_armed = False
        self._shots_since_step = 0
        self._last_synced_shots_per_step = None

    def _advance_raster(self):
        """Arm (once) and step the raster on the first shot of each group.

        The group counter deliberately persists across queue end: there
        is no transition_to_manual between queued shots, and a paused or
        resumed queue should not restart the group count.
        """
        if not self.remote_comms.connected:
            raise Exception(
                "Cannot advance raster: not connected to rastering GUI.\n"
                "Check that the rastering GUI is running."
            )

        if self._shots_since_step == 0:
            if not self._raster_armed:
                # Arm in step mode (value 0). The server arms from
                # scratch when no raster is active; typed failures
                # (no_raster_configured, not_calibrated, ...) raise
                # loudly via _check_response.
                response = self.remote_comms.program_value(
                    "arm_raster", 0, wait_for_lock=True
                )
                self._check_response(response, "raster_arm")
                self._raster_armed = True
                # A GUI that restarted mid-queue forgot N, so re-teach it
                # alongside the re-arm. Non-fatal by construction:
                # _send_shots_per_step swallows and warns, because N is
                # display-only on the GUI — BLACS owns the stepping.
                self._send_shots_per_step()

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
                # Reset so a re-queue after "sequence complete" cleanly
                # re-arms a fresh raster from the beginning of the path.
                self._raster_armed = False
                self._shots_since_step = 0
                raise Exception(
                    "Raster sequence complete — no more points in the path.\n"
                    "Queueing more shots will re-arm and restart the raster "
                    "from the beginning."
                )
            # A GUI restart mid-queue tears down the armed raster, so the
            # server answers raster_not_active. Drop the armed flag so the
            # next attempt re-arms from scratch — the shot still fails loudly.
            if (response.get("error") or {}).get("code") == "raster_not_active":
                self._raster_armed = False

            # Any non-SUCCESS status -> raise via the v2-aware checker
            # (handles ERROR/REJECTED/TIMEOUT/UNKNOWN_CONNECTION uniformly).
            self._check_response(response, "raster_move_to_next")

            self.logger.debug(f"Raster move_to_next: {response}")

        # Advance the counter only after a successful step (or on a
        # non-step shot): a failed step leaves the counter at 0, so the
        # retried shot still performs a step and never fires at the
        # previous position. The point whose move failed is skipped,
        # though — the GUI consumes the path point before enqueuing the
        # move, so the retry steps to the NEXT point.
        self._shots_since_step = (self._shots_since_step + 1) % self.shots_per_step

    def transition_to_buffered(self, device_name, h5_filepath, front_panel_values, fresh):
        if not self.enable_comms:
            return {}

        self.h5_filepath = h5_filepath

        # Step 1: Advance raster if enabled (arm once, step every
        # shots_per_step-th shot).
        if self.raster_mode:
            self._advance_raster()

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

