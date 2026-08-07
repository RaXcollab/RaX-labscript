import labscript_utils.h5_lock
import h5py

from user_devices.RemoteControl.blacs_workers import RemoteControlWorker

# Raster provenance the GUI piggybacks on the move_to_next reply
# (SystemController.raster_point_meta). Whitelisted so envelope fields
# (status, id, ...) never leak into the shot record. `frame` names the frame
# target_xy is in ('pixel' calibrated, 'motor' passthrough) — without it the
# two are indistinguishable in the shot h5.
# in_place: the GUI fired the shot at the laser's current position (operator
# holds control, nothing armed). Without it in the whitelist a fire-in-place
# shot is byte-identical in the h5 to a shot with no raster at all.
RASTER_META_KEYS = ("point_index", "path_len", "target_xy", "frame",
                    "calibration_matrix", "calibration_offset", "in_place")

# The coord pair is written as ONE compound PROGRAM_VALUE: [x, y] in the
# target/pixel frame. Per-axis writes make the GUI pair each new coord with its
# cached partner, so the motors traverse (x_new, y_old) — a composite that
# can map outside travel even when both endpoints are legal (2026-08-04
# incident). The GUI also accepts an optional args['frame'] ('pixel'
# default, 'motor' bypasses calibration); BLACS only ever writes target-frame
# coords, and RemoteCommunication.program_value fixes args to wait_for_lock,
# so we rely on the default and send no frame tag.
COORD_PAIR = ("laser_raster_x_coord", "laser_raster_y_coord")
COMPOUND_XY = "laser_raster_xy"


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
        # "blacs" | "local". Workerargs are set as instance attributes before
        # init() runs, so normalize rather than clobber.
        self.raster_control = str(getattr(self, "raster_control", "blacs"))
        self._shots_since_step = 0
        self._raster_armed = False
        # Last N the GUI acknowledged; None means "the GUI doesn't know N".
        self._last_synced_shots_per_step = None
        # Provenance of the point the current group stepped to (see
        # RASTER_META_KEYS); every shot in the group is stamped with it.
        self._raster_meta = {}

    def connect_to_remote(self):
        """Connect, then push the current raster controls to the GUI.

        A fresh connection may be a restarted GUI, so anything we believed
        about its armed state is void. Syncing here is what makes a
        restored-checked checkbox arm the GUI at BLACS startup rather than
        at the first shot.

        The re-sync inherits the Control gate: the arm lives inside
        _sync_raster_mode_to_gui, which now requires raster_control ==
        "blacs". This reconnect path must NOT grow its own arm call.
        """
        connected = super().connect_to_remote()
        if connected:
            self._raster_armed = False
            self._last_synced_shots_per_step = None
            self._sync_raster_mode_to_gui()
        return connected

    def program_manual(self, front_panel_values):
        """Manual mode: send the coord pair as ONE compound write.

        Same loop as the base, over a write list where both coords are
        replaced by a single COMPOUND_XY write — so a refused pair reaches
        _on_program_manual_error exactly once (courtesy policy intact) and
        any other output channel keeps its own per-channel write. A panel
        carrying only one coord keeps the single-axis path: never fabricate
        the partner.
        """
        if not self.remote_comms.connected:
            return {}
        if not self._initial_fetch_done:
            return {}  # Don't overwrite server values before first fetch

        writes = [(c, front_panel_values[c])
                  for c in self.child_output_connections]
        if all(c in front_panel_values for c in COORD_PAIR):
            xy = [float(front_panel_values[c]) for c in COORD_PAIR]
            writes = [(COMPOUND_XY, xy)] + [
                w for w in writes if w[0] not in COORD_PAIR]

        for connection, value in writes:
            response = self.remote_comms.program_value(
                connection, value, wait_for_lock=False)
            try:
                self._check_response(
                    response, f"program_manual({connection}={value})")
            except Exception as exc:
                self._on_program_manual_error(connection, value, response, exc)
        return {}

    def _on_program_manual_error(self, connection, value, response, exc):
        """Front-panel re-asserts are courtesy writes -- never fail the tab.

        BLACS pushes the full front panel through program_manual on the
        queue-abort path (device_base_class abort_* -> program_device) and
        at tab startup. A refused motor move -- e.g. re-asserting an echoed
        coordinate that maps a hair outside travel because the calibration
        cross-terms make target->motor partner-dependent (2026-08-04
        incident) -- must not red-error the tab (a sticky tab error blocks
        ALL later shots until dismissed), and must not leave the sibling
        axis unsent. Shot programming keeps its strict raise-on-failure
        semantics in transition_to_buffered.
        """
        self.logger.warning(
            f"program_manual({connection}={value}) refused by the "
            f"rastering GUI; continuing with remaining channels: {exc}"
        )

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

    def update_raster_control(self, raster_control):
        """Control changed at the tab. Releasing to the operator sends
        disarm_raster, which the GUI now treats as 'release ownership,
        keep the path' rather than 'destroy the raster'."""
        self.raster_control = str(raster_control)
        if self.raster_control == "local":
            self._raster_armed = False
            try:
                response = self.remote_comms.program_value("disarm_raster", 1)
                self._check_response(response, "raster_release")
            except Exception as e:
                # Never raise from a settings change: the GUI may be closed.
                self.logger.warning(f"Could not release raster to GUI: {e}")
        else:
            self._sync_raster_mode_to_gui()

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

        # Gated on Control too: arm_raster's already-armed branch sets
        # _raster_source = "remote" on the GUI, so an un-gated arm here would
        # seize the raster back from an operator who just took local control.
        if self.raster_mode and self.raster_control == "blacs":
            if not self._raster_armed:
                try:
                    response = self.remote_comms.program_value(
                        "arm_raster", 0, wait_for_lock=True
                    )
                    self._check_response(response, "raster_arm(settings)")
                    dropped = response.get("dropped") if response else None
                    if dropped:
                        # The GUI drops points outside motor travel at arm
                        # time; without this line the drop is visible only on
                        # the GUI status bar, never to an operator watching
                        # BLACS.
                        self.logger.info(
                            f"Raster armed with {response.get('armed')} points; "
                            f"{dropped} dropped (outside motor travel).")
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

        # Disabled or Control=Local. Under local, push the release
        # UNCONDITIONALLY: connect_to_remote lands here with was_enabled=None
        # and _raster_armed freshly cleared, so the old guard sent nothing --
        # a restored Control=Local never reached the GUI, whose ownership
        # flag then let move_to_next keep advancing (shots_per_step times
        # faster, since local queries every shot). The was_enabled/_raster_armed
        # guard remains for the blacs-control case only (spinbox jiggle with
        # Raster Mode off must not touch the GUI).
        if self.raster_control == "local" or was_enabled or self._raster_armed:
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

        Path end is normal operation, not an error. Since 2026-08-03 the
        GUI wraps natively: a step past the last point (any source, since
        2026-08-04) rewinds the cursor to point 0, the armed pattern is
        immutable until a fresh arm, and BLACS never sees `finished`. The finished->re-arm
        branch below is kept as a fallback (older GUI builds); that path
        rebuilds from the GUI's live settings. One pass = queue exactly
        path_len * shots_per_step shots from a fresh arm — the cursor
        and group counter persist across queue end.

        The group counter deliberately persists across queue end: there
        is no transition_to_manual between queued shots, and a paused or
        resumed queue should not restart the group count.
        """
        if not self.remote_comms.connected:
            raise Exception(
                "Cannot advance raster: not connected to rastering GUI.\n"
                "Check that the rastering GUI is running."
            )

        # Under local control the group counter has no job -- BLACS is not
        # advancing anything, it is only asking where the laser is. Skipping
        # shots 2..N of a group would stamp them with a point the operator has
        # since stepped away from. Keep mutating the counter below so the group
        # phase survives a flip back to BLACS mid-queue.
        if self._shots_since_step == 0 or self.raster_control == "local":
            for rearmed in (False, True):
                if not self._raster_armed and self.raster_control == "blacs":
                    # Arm in step mode (value 0). The server arms from
                    # scratch when no raster is active; typed failures
                    # (no_raster_configured, not_calibrated, ...) raise
                    # loudly via _check_response.
                    response = self.remote_comms.program_value(
                        "arm_raster", 0, wait_for_lock=True
                    )
                    self._check_response(response, "raster_arm")
                    dropped = response.get("dropped") if response else None
                    if dropped:
                        # The GUI drops points outside motor travel at arm
                        # time; without this line the drop is visible only on
                        # the GUI status bar, never to an operator watching
                        # BLACS.
                        self.logger.info(
                            f"Raster armed with {response.get('armed')} points; "
                            f"{dropped} dropped (outside motor travel).")
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
                # The exhausting move_to_next moves no motor, so the wrapped
                # step on the retry is the first motion of the new pass.
                status = response.get("status", "")
                if status == "SUCCESS" and response.get("finished") is True:
                    self._raster_armed = False
                    self._shots_since_step = 0
                    if rearmed:
                        raise Exception(
                            "Raster re-armed but immediately reported "
                            "'finished' — the raster path appears to be "
                            "empty. Check the path in the rastering GUI."
                        )
                    self.logger.info(
                        "Raster path exhausted — re-arming to repeat the "
                        "pattern from the beginning."
                    )
                    continue
                # A GUI restart mid-queue tears down the armed raster, so the
                # server answers raster_not_active. Drop the armed flag so the
                # next attempt re-arms from scratch — the shot still fails loudly.
                if (response.get("error") or {}).get("code") == "raster_not_active":
                    self._raster_armed = False

                # Any non-SUCCESS status -> raise via the v2-aware checker
                # (handles ERROR/REJECTED/TIMEOUT/UNKNOWN_CONNECTION uniformly).
                self._check_response(response, "raster_move_to_next")

                self._raster_meta = {k: response[k] for k in RASTER_META_KEYS
                                     if k in response}

                self.logger.debug(f"Raster move_to_next: {response}")
                break

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
                writes = [(c, float(table[0][c])) for c in table.dtype.names]
                # Both coords in this shot's table -> one atomic pair. A
                # one-column table (generate_code emits a column only for
                # channels the sequence set) keeps the single-axis path: the
                # missing axis must NEVER be filled from front_panel_values,
                # which can be seconds-stale echo. The GUI pairs a single-axis
                # move with a fresh encoder read itself.
                if all(c in table.dtype.names for c in COORD_PAIR):
                    xy = [float(table[0][c]) for c in COORD_PAIR]
                    writes = [(COMPOUND_XY, xy)] + [
                        w for w in writes if w[0] not in COORD_PAIR]
                # Gated on Control, NOT Raster Mode: "Raster off + Control
                # BLACS" must still allow remote position feeding.
                coord_writes = any(
                    c == COMPOUND_XY or c in COORD_PAIR for c, _ in writes)
                # Raise only when the sequence actually programs COORDINATES:
                # gating on mere table presence would fire, with a message
                # about coordinates, on a future non-coordinate child.
                if self.raster_control == "local" and coord_writes:
                    raise Exception(
                        "Sequence programs explicit raster coordinates, but "
                        "Control is set to Local.\n"
                        "The operator is hand-driving the raster; a remote "
                        "position write would fight them.\n"
                        "Tick 'BLACS drives raster' in this tab (or hand "
                        "control back at the rastering GUI) and resume."
                    )
                for connection, value in writes:
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

    def post_experiment(self):
        """Stamp which raster point this shot was fired at.

        The stamp must land here, not in transition_to_buffered: /data is
        owned by the queue manager, which creates it unconditionally once
        the shot finishes (blacs/blacs/experiment_queue.py). A device that
        creates /data earlier crashes the queue manager and pauses the queue.
        """
        result = super().post_experiment()

        # Every shot of the group carries the point its group stepped to; the
        # calibration rides along so target coords stay interpretable if it
        # changes later.
        if self.raster_mode and self._raster_meta and self.h5_filepath:
            with h5py.File(self.h5_filepath, 'a') as f:
                group = f.require_group(f'/data/{self.device_name}/raster')
                group.attrs.update(self._raster_meta)

        # A comms-disabled shot returns from transition_to_buffered before it
        # assigns h5_filepath, and _raster_meta deliberately survives the shot
        # group — so without this clear, that shot re-stamps the PREVIOUS
        # shot's file.
        self.h5_filepath = None

        return result

