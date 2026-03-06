import re
import threading
import time

import zmq
from qtutils.qt import QtWidgets, QtCore

from blacs.device_base_class import define_state, MODE_MANUAL
from user_devices.RemoteControl.blacs_tabs import (
    RemoteControlTab,
    DynamicStackedWidget,
    FailureButton,
    _PubSubSignalBridge,
)

# Regex to split "YAG_1_voltage" → ("YAG_1", "voltage")
_PREFIX_RE = re.compile(r'^(.+?_\d+)_(.+)$')

# Channel classification by suffix
_BINARY_OUTPUTS = {'lamps', 'shutter', 'qswitch'}
_MODE_OUTPUTS = {'lamp_mode', 'qswitch_mode'}
_COMMAND_OUTPUTS = {'warmup', 'start_lasing', 'stop'}

# Human-readable labels for toggle buttons and monitor indicators
_TOGGLE_LABELS = {
    'lamps':   ('Lamps: ON',    'Lamps: OFF'),
    'shutter': ('Shutter: ON',  'Shutter: OFF'),
    'qswitch': ('Q-Switch: ON', 'Q-Switch: OFF'),
}
_MONITOR_LABELS = {
    'lamps_monitor':   ('active',  'standby'),
    'shutter_monitor': ('open',    'closed'),
    'qswitch_monitor': ('armed',   'disarmed'),
}

# Mode combo box options: {suffix: [(display_text, ...), ...]}
_MODE_OPTIONS = {
    'lamp_mode':    ["Internal (0)", "External (1)"],
    'qswitch_mode': ["Internal (0)", "Burst (1)", "External (2)"],
}

# Temperature thresholds for color coding
_TEMP_COLD = 37.0    # blue
_TEMP_WARM = 39.0    # gold → green transition


class BigSkyTab(RemoteControlTab):
    """BLACS tab for the BigSky YAG laser hub.

    Overrides the generic RemoteControlTab layout to provide:
    - Toggle buttons for binary controls (lamps, shutter, qswitch)
    - Combo boxes for mode selectors (lamp_mode, qswitch_mode)
    - Color-coded temperature monitor
    - Per-laser group boxes with integrated monitors
    - Hidden command channels (warmup, start_lasing, stop)
    """

    # ── GUI setup ─────────────────────────────────────────────────────

    def initialise_GUI(self):
        # ── 1. Connection table properties ──
        connection_table = self.settings['connection_table']
        device = connection_table.find_by_name(self.device_name)
        self.properties = device.properties

        self.mock = self.properties['mock']
        self.host = self.properties['host']
        self.reqrep_port = self.properties['reqrep_port']
        self.pubsub_port = self.properties['pubsub_port']

        self.reqrep_connected = False
        self.pubsub_connected = False

        # ── 2. PubSub signal bridge ──
        self._pubsub_bridge = _PubSubSignalBridge()
        self._pubsub_bridge.pubsub_status_changed.connect(self._on_pubsub_status_changed)
        self._pubsub_bridge.monitor_value_received.connect(self._on_monitor_value_received)

        # ── 3. Discover child devices ──
        self.child_output_devices = []
        self.child_monitor_devices = []
        self.child_output_connections = []
        self.child_monitor_connections = []

        for child_device in device.child_list.values():
            if child_device.device_class == "RemoteAnalogOut":
                self.child_output_devices.append(child_device)
                self.child_output_connections.append(child_device.parent_port)
            elif child_device.device_class == "RemoteAnalogMonitor":
                self.child_monitor_devices.append(child_device)
                self.child_monitor_connections.append(child_device.parent_port)

        # ── 4. Create AO objects for ALL channels ──
        AO_prop = {}
        for dev in self.child_output_devices:
            cp = dev._properties
            lo, hi = cp["limits"]
            AO_prop[dev.parent_port] = {
                'base_unit': cp["units"],
                'min': lo,
                'max': hi,
                'step': cp["step_size"],
                'decimals': cp["decimals"],
            }
        self.create_analog_outputs(AO_prop)

        AM_prop = {}
        for dev in self.child_monitor_devices:
            cp = dev._properties
            lo, hi = cp["limits"]
            AM_prop[dev.parent_port] = {
                'base_unit': cp["units"],
                'min': lo,
                'max': hi,
                'step': cp["step_size"],
                'decimals': cp["decimals"],
            }
        self.create_analog_outputs(AM_prop)

        # ── 5. Create standard spinbox widgets for voltage only ──
        voltage_props = {}
        for conn in self.child_output_connections:
            m = _PREFIX_RE.match(conn)
            if m and m.group(2) == 'voltage':
                voltage_props[conn] = {}
        self.AO_widgets = self.create_analog_widgets(voltage_props)
        # Hide the built-in label from each voltage widget — redundant inside group box
        for widget in self.AO_widgets.values():
            if hasattr(widget, '_label'):
                widget._label.hide()

        # No standard monitor widgets — we use custom labels
        self.AM_widgets = {}

        # ── 6. Discover laser prefixes and build custom layout ──
        self._toggle_buttons = {}    # {connection: QPushButton}
        self._mode_combos = {}       # {connection: QComboBox}
        self._monitor_labels = {}    # {connection: QLabel}
        self._temp_labels = {}       # {connection: QLabel}
        self._voltage_labels = {}    # {connection: QLabel}
        self._recently_changed = {}  # {connection: monotonic timestamp}
        self._lamps_active = {}     # {prefix: bool} — tracks per-laser lamp state
        self._input_enabled = True  # tracks "Disable Input" checkbox state
        self._laser_groups = {}       # {prefix: QGroupBox} — stored from _create_laser_group
        self._last_monitor_time = {}  # {prefix: float} — time.monotonic() of last PUB-SUB value
        self._laser_online = {}       # {prefix: bool} — tracks online state to avoid redundant updates
        self._action_buttons = {}     # {prefix: {'stop': btn, 'warmup': btn, 'arm': btn}}
        self._keep_warm = {}          # {prefix: bool} — Auto Arm Ext state
        self._keep_warm_buttons = {}  # {prefix: QCheckBox}
        self._keep_warm_temp = {}     # {prefix: bool} — Auto Keep Warm state
        self._keep_warm_temp_buttons = {}  # {prefix: QCheckBox}
        self._warmup_triggered = {}   # {prefix: bool} — True while warmup active for cold episode

        laser_prefixes = sorted(set(
            m.group(1) for c in self.child_output_connections
            if (m := _PREFIX_RE.match(c))
        ))

        self._laser_widget = QtWidgets.QWidget()
        laser_layout = QtWidgets.QVBoxLayout()
        laser_layout.setContentsMargins(2, 2, 2, 2)
        laser_layout.setSpacing(4)
        self._laser_widget.setLayout(laser_layout)

        for prefix in laser_prefixes:
            group = self._create_laser_group(prefix)
            laser_layout.addWidget(group)

        # ── 6b. Per-laser health check timer (30s stale threshold) ──
        self._laserHealthTimer = QtCore.QTimer()
        self._laserHealthTimer.timeout.connect(self._check_laser_health)
        self._laserHealthTimer.start(10000)

        # ── 7. Reconnect buttons ──
        self.reconnect_reqrep_button = QtWidgets.QPushButton(
            "Click Here to Reconnect\nREQ-REP socket"
        )
        self.reconnect_reqrep_button.setStyleSheet("background-color: #ffcccc;")
        self.reconnect_reqrep_button.clicked.connect(self.reconnect_reqrep)
        self.reconnect_reqrep_button.hide()

        self.reconnect_pubsub_button = QtWidgets.QPushButton(
            "Click Here to Reconnect\nPUB-SUB socket"
        )
        self.reconnect_pubsub_button.setStyleSheet("background-color: #ffcccc;")
        self.reconnect_pubsub_button.clicked.connect(self.reconnect_pubsub)
        self.reconnect_pubsub_button.hide()

        # ── 8. Layout assembly ──
        self.main_gui_layout = self.get_tab_layout()

        self.ao_placeholder = DynamicStackedWidget()
        self.ao_placeholder.addWidget(self._laser_widget)
        self.ao_placeholder.addWidget(self.reconnect_reqrep_button)

        # Dummy widget so parent's _update_gui_status can reference am_placeholder
        self._am_dummy = QtWidgets.QWidget()
        self.am_placeholder = DynamicStackedWidget()
        self.am_placeholder.addWidget(self._am_dummy)
        self.am_placeholder.addWidget(self.reconnect_pubsub_button)

        # Set aliases so parent's _update_gui_status works
        self.ao_toolpalette_widget = self._laser_widget
        self.am_toolpalette_widget = self._am_dummy

        self.main_gui_layout.insertWidget(0, self.ao_placeholder)
        self.main_gui_layout.insertWidget(1, self.am_placeholder)

        # ── 9. Disable Input checkbox ──
        self.comms_check_box = QtWidgets.QCheckBox("Disable Input")
        self.main_gui_layout.addWidget(self.comms_check_box)
        self.comms_check_box.toggled.connect(self.on_checkbox_toggled)

        # ── 10. Initially hidden ──
        self.ao_placeholder.hide()
        self.am_placeholder.hide()
        self.comms_check_box.hide()

        # ── 11. Failure button ──
        self.failed_button = FailureButton()
        self.failed_button.connect_clicked(lambda: self.connect_to_remote())
        self.main_gui_layout.addWidget(self.failed_button)
        self.failed_button.hide()

    # ── Per-laser group box builder ───────────────────────────────────

    def _create_laser_group(self, prefix):
        """Build a QGroupBox with controls and monitors for one laser."""
        group = QtWidgets.QGroupBox(prefix)
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # ── Temperature monitor ──
        temp_conn = f"{prefix}_temperature_monitor"
        if temp_conn in [d.parent_port for d in self.child_monitor_devices]:
            temp_label = QtWidgets.QLabel("Temperature: -- °C")
            temp_label.setStyleSheet("font-weight: bold; padding: 2px;")
            self._temp_labels[temp_conn] = temp_label
            layout.addWidget(temp_label)

        # ── Voltage row: label + spinbox + monitor ──
        voltage_conn = f"{prefix}_voltage"
        voltage_mon = f"{prefix}_voltage_monitor"
        voltage_row = QtWidgets.QHBoxLayout()

        voltage_row.addWidget(QtWidgets.QLabel("Voltage:"))
        if voltage_conn in self.AO_widgets:
            voltage_row.addWidget(self.AO_widgets[voltage_conn])

        voltage_label = QtWidgets.QLabel("(monitor: -- V)")
        voltage_label.setStyleSheet("color: #666; padding-left: 8px;")
        self._voltage_labels[voltage_mon] = voltage_label
        voltage_row.addWidget(voltage_label)
        voltage_row.addStretch()
        layout.addLayout(voltage_row)

        # ── Toggle buttons row: lamps, shutter, qswitch ──
        toggle_row = QtWidgets.QHBoxLayout()
        toggle_row.setSpacing(8)
        for suffix in ('lamps', 'shutter', 'qswitch'):
            conn = f"{prefix}_{suffix}"
            if conn not in self._AO:
                continue

            col = QtWidgets.QVBoxLayout()
            col.setSpacing(2)

            # Toggle button
            btn = QtWidgets.QPushButton(_TOGGLE_LABELS[suffix][1])  # start OFF
            btn.setCheckable(True)
            btn.setMinimumWidth(100)
            self._style_toggle_btn(btn, False)
            btn.toggled.connect(lambda checked, c=conn: self._on_toggle(c, checked))
            self._toggle_buttons[conn] = btn
            col.addWidget(btn)

            # Monitor indicator below
            mon_conn = f"{prefix}_{suffix}_monitor"
            mon_label = QtWidgets.QLabel("● --")
            mon_label.setAlignment(QtCore.Qt.AlignCenter)
            mon_label.setStyleSheet("color: #999; font-size: 10px;")
            self._monitor_labels[mon_conn] = mon_label
            col.addWidget(mon_label)

            toggle_row.addLayout(col)

        toggle_row.addStretch()
        layout.addLayout(toggle_row)

        # ── Mode selectors row ──
        mode_row = QtWidgets.QHBoxLayout()
        mode_row.setSpacing(16)

        for suffix in ('lamp_mode', 'qswitch_mode'):
            conn = f"{prefix}_{suffix}"
            if conn not in self._AO:
                continue

            label_text = "Lamp Mode:" if suffix == 'lamp_mode' else "QS Mode:"
            mode_label = QtWidgets.QLabel(label_text)

            combo = QtWidgets.QComboBox()
            combo.addItems(_MODE_OPTIONS[suffix])
            combo.currentIndexChanged.connect(
                lambda idx, c=conn: self._on_mode_change(c, idx)
            )
            self._mode_combos[conn] = combo

            mode_row.addWidget(mode_label)
            mode_row.addWidget(combo)

        mode_row.addStretch()
        layout.addLayout(mode_row)

        # ── Action buttons + auto checkboxes row ──
        # Buttons on the left, two checkboxes stacked vertically on the right,
        # sized to match the button row height.
        action_row = QtWidgets.QHBoxLayout()
        action_row.setSpacing(8)

        stop_btn = QtWidgets.QPushButton("STOP")
        stop_btn.setMinimumWidth(70)
        stop_btn.setMinimumHeight(36)
        stop_btn.setStyleSheet(
            "QPushButton { background-color: #D32F2F; color: white; "
            "font-weight: bold; border-radius: 4px; padding: 8px; }"
        )
        stop_btn.clicked.connect(
            lambda _, p=prefix: self._on_stop_clicked(p)
        )
        action_row.addWidget(stop_btn)

        warmup_btn = QtWidgets.QPushButton("Warmup")
        warmup_btn.setMinimumWidth(90)
        warmup_btn.setMinimumHeight(36)
        warmup_btn.clicked.connect(
            lambda _, p=prefix: self._on_warmup_clicked(p)
        )
        action_row.addWidget(warmup_btn)

        arm_btn = QtWidgets.QPushButton("Arm Ext")
        arm_btn.setMinimumWidth(90)
        arm_btn.setMinimumHeight(36)
        arm_btn.clicked.connect(
            lambda _, p=prefix: self._on_arm_external_clicked(p)
        )
        action_row.addWidget(arm_btn)

        # Store refs and set initial (inactive) styles
        self._action_buttons[prefix] = {
            'stop': stop_btn, 'warmup': warmup_btn, 'arm': arm_btn,
        }
        self._style_action_buttons(prefix, warming=False, armed=False)

        # Checkboxes stacked vertically to match button row height
        cb_col = QtWidgets.QVBoxLayout()
        cb_col.setContentsMargins(0, 0, 0, 0)
        cb_col.setSpacing(0)

        auto_arm_cb = QtWidgets.QCheckBox("Auto Arm Ext")
        auto_arm_cb.setToolTip(
            "Auto-arm this laser to external trigger before each shot queue."
        )
        auto_arm_cb.setStyleSheet(
            "font-weight: bold; font-size: 10px; padding: 1px;"
        )
        auto_arm_cb.toggled.connect(
            lambda checked, p=prefix: self._on_keep_warm_toggle(p, checked)
        )
        self._keep_warm_buttons[prefix] = auto_arm_cb
        self._keep_warm[prefix] = False
        cb_col.addWidget(auto_arm_cb)

        auto_keep_warm_cb = QtWidgets.QCheckBox("Auto Keep Warm")
        auto_keep_warm_cb.setToolTip(
            "While in manual mode, automatically enter warmup\n"
            "if temperature drops below 37°C."
        )
        auto_keep_warm_cb.setStyleSheet("font-size: 10px; padding: 1px;")
        auto_keep_warm_cb.toggled.connect(
            lambda checked, p=prefix: self._on_keep_warm_temp_toggle(p, checked)
        )
        self._keep_warm_temp_buttons[prefix] = auto_keep_warm_cb
        self._keep_warm_temp[prefix] = False
        self._warmup_triggered[prefix] = False
        cb_col.addWidget(auto_keep_warm_cb)

        action_row.addLayout(cb_col)
        action_row.addStretch()
        layout.addLayout(action_row)

        group.setLayout(layout)

        # Store ref and start offline — restored on first PUB-SUB message
        self._laser_groups[prefix] = group
        self._laser_online[prefix] = False
        group.setEnabled(False)
        group.setTitle("%s (OFFLINE)" % prefix)

        return group

    # ── Toggle / combo callbacks ──────────────────────────────────────

    def _on_toggle(self, connection, checked):
        """User toggled a binary control button."""
        self._style_toggle(connection, checked)
        self._recently_changed[connection] = time.monotonic()
        self._AO[connection].set_value(1.0 if checked else 0.0, program=True)

    def _on_mode_change(self, connection, index):
        """User changed a mode combo box."""
        self._recently_changed[connection] = time.monotonic()
        self._AO[connection].set_value(float(index), program=True)

    # ── Auto Re-Arm Ext ────────────────────────────────────────────────

    def _on_keep_warm_toggle(self, prefix, checked):
        """User toggled Auto Re-Arm Ext for a laser.

        Only sets the flag and updates interlocks. Does NOT send hardware
        commands — use the Warmup/Arm Ext/Stop buttons for that.
        """
        self._keep_warm[prefix] = checked
        self._update_keep_warm_interlocks(prefix)
        # Sync the flag to the worker so transition_to_buffered knows
        self._sync_keep_warm_to_worker(prefix, checked)

    @define_state(MODE_MANUAL, True)
    def _sync_keep_warm_to_worker(self, prefix, state):
        yield (self.queue_work(
            self.primary_worker, 'update_keep_warm', prefix, state
        ))

    # ── Auto Keep Warm (tab-side temperature monitoring) ────────────

    def _on_keep_warm_temp_toggle(self, prefix, checked):
        """User toggled Auto Keep Warm for a laser."""
        self._keep_warm_temp[prefix] = checked
        if not checked:
            self._warmup_triggered[prefix] = False

    def _evaluate_keep_warm(self, prefix, temp):
        """Check if Auto Keep Warm should trigger warmup. Runs on GUI thread.

        Uses hysteresis to prevent oscillation:
        - Triggers warmup when temp drops below _TEMP_COLD (37°C)
        - Resets trigger flag when temp rises to _TEMP_WARM (39°C)

        The self.mode check is GIL-atomic (single LOAD_ATTR on an int) and
        safe to read from the GUI thread without locking.
        """
        if not self._keep_warm_temp.get(prefix, False):
            return
        if not self._laser_online.get(prefix, False):
            return
        # Only act in manual mode — during buffered shots, let the shot run
        if self.mode != MODE_MANUAL:
            return

        if temp < _TEMP_COLD and not self._warmup_triggered.get(prefix, False):
            self._warmup_triggered[prefix] = True
            self.logger.info(
                "Auto Keep Warm: %s cold (%.1fC), triggering warmup", prefix, temp
            )
            self._send_keep_warm_warmup(prefix)
        elif temp >= _TEMP_WARM:
            # Hysteresis: reset trigger only when fully warm
            if self._warmup_triggered.get(prefix, False):
                self._warmup_triggered[prefix] = False
                self.logger.debug(
                    "Auto Keep Warm: %s warm (%.1fC), trigger reset", prefix, temp
                )

    @define_state(MODE_MANUAL, True)
    def _send_keep_warm_warmup(self, prefix):
        """Queue warmup command to worker for Auto Keep Warm.

        Decorated with @define_state(MODE_MANUAL, True) so it only executes
        in manual mode. If queued during a mode transition (e.g., a shot just
        started), the event stays queued and fires when returning to manual.
        The stale-event guard below prevents firing if the user unchecked
        Auto Keep Warm while the event was waiting.
        """
        # Stale-event guard: user may have unchecked while event was queued
        if not self._keep_warm_temp.get(prefix, False):
            return
        yield (self.queue_work(
            self.primary_worker, 'restore_warmup_from_tab', prefix
        ))

    # ── Action buttons: Stop / Warmup / Arm Ext ─────────────────────
    # These use fire-and-forget channels which are skipped by program_manual,
    # so we send them directly via the worker's _send_cmd method.

    def _on_stop_clicked(self, prefix):
        """Send stop (standby) command directly to the worker."""
        self._send_action_to_worker(prefix, 'stop')

    def _on_warmup_clicked(self, prefix):
        """Send warmup command directly to the worker."""
        self._send_action_to_worker(prefix, 'warmup')

    def _on_arm_external_clicked(self, prefix):
        """Send arm-external (start_lasing) command directly to the worker."""
        self._send_action_to_worker(prefix, 'start_lasing')

    @define_state(MODE_MANUAL, True)
    def _send_action_to_worker(self, prefix, action):
        yield (self.queue_work(
            self.primary_worker, 'send_action', prefix, action
        ))

    def _style_action_buttons(self, prefix, warming, armed):
        """Update Warmup and Arm Ext button colors based on laser state."""
        btns = self._action_buttons.get(prefix)
        if not btns:
            return
        # Warmup: blue (cold/inactive) -> orange (warming)
        if warming:
            btns['warmup'].setStyleSheet(
                "QPushButton { background-color: #FF9800; color: white; "
                "font-weight: bold; border-radius: 4px; padding: 8px; }"
            )
        else:
            btns['warmup'].setStyleSheet(
                "QPushButton { background-color: #64B5F6; color: white; "
                "font-weight: bold; border-radius: 4px; padding: 8px; }"
            )
        # Arm Ext: gray (not armed) -> green (armed)
        if armed:
            btns['arm'].setStyleSheet(
                "QPushButton { background-color: #4CAF50; color: white; "
                "font-weight: bold; border-radius: 4px; padding: 8px; }"
            )
        else:
            btns['arm'].setStyleSheet(
                "QPushButton { background-color: #BDBDBD; color: #333; "
                "font-weight: bold; border-radius: 4px; padding: 8px; }"
            )

    def _update_action_button_state(self, prefix):
        """Determine laser state from cached monitor values and style buttons."""
        lamps = self._lamps_active.get(prefix, False)
        # Check shutter and qswitch from toggle button state
        shutter_conn = f"{prefix}_shutter"
        qswitch_conn = f"{prefix}_qswitch"
        shutter_on = (shutter_conn in self._toggle_buttons and
                      self._toggle_buttons[shutter_conn].isChecked())
        qswitch_on = (qswitch_conn in self._toggle_buttons and
                      self._toggle_buttons[qswitch_conn].isChecked())

        armed = lamps and shutter_on and qswitch_on
        warming = lamps and not shutter_on and not qswitch_on
        self._style_action_buttons(prefix, warming=warming, armed=armed)

    def _update_keep_warm_interlocks(self, prefix):
        """Disable manual controls when Keep Warm is active."""
        kw_on = self._keep_warm.get(prefix, False)
        for suffix in ('lamps', 'shutter', 'qswitch'):
            conn = f"{prefix}_{suffix}"
            if conn in self._toggle_buttons:
                self._toggle_buttons[conn].setEnabled(
                    self._input_enabled and not kw_on
                )
        for suffix in ('lamp_mode', 'qswitch_mode'):
            conn = f"{prefix}_{suffix}"
            if conn in self._mode_combos:
                lamps_on = self._lamps_active.get(prefix, False)
                self._mode_combos[conn].setEnabled(
                    self._input_enabled and not kw_on and not lamps_on
                )

    # ── Styling helpers ───────────────────────────────────────────────

    def _style_toggle_btn(self, btn, is_on):
        """Apply ON/OFF styling to a toggle button."""
        if is_on:
            btn.setStyleSheet(
                "QPushButton { background-color: #4CAF50; color: white; "
                "font-weight: bold; border-radius: 4px; padding: 6px; }"
            )
        else:
            btn.setStyleSheet(
                "QPushButton { background-color: #ccc; color: #333; "
                "border-radius: 4px; padding: 6px; }"
            )

    def _style_toggle(self, connection, is_on):
        """Update toggle button text and color."""
        btn = self._toggle_buttons[connection]
        m = _PREFIX_RE.match(connection)
        suffix = m.group(2) if m else connection
        labels = _TOGGLE_LABELS.get(suffix, (f"{suffix}: ON", f"{suffix}: OFF"))
        btn.setText(labels[0] if is_on else labels[1])
        self._style_toggle_btn(btn, is_on)

    def _style_temp(self, temp_label, value):
        """Apply temperature color coding."""
        if value < _TEMP_COLD:
            color = "#2196F3"  # blue
        elif value < _TEMP_WARM:
            color = "#FF9800"  # gold
        else:
            color = "#4CAF50"  # green
        temp_label.setText(f"Temperature: {value:.1f} °C")
        temp_label.setStyleSheet(
            f"font-weight: bold; padding: 2px; color: {color};"
        )

    def _style_monitor(self, connection, value):
        """Update a binary monitor indicator label."""
        label = self._monitor_labels.get(connection)
        if label is None:
            return
        m = _PREFIX_RE.match(connection)
        suffix = m.group(2) if m else connection
        labels = _MONITOR_LABELS.get(suffix, ('ON', 'OFF'))
        is_on = float(value) > 0.5
        text = labels[0] if is_on else labels[1]
        color = "#4CAF50" if is_on else "#999"
        label.setText(f"● {text}")
        label.setStyleSheet(f"color: {color}; font-size: 10px; text-align: center;")

    # ── Override: update AO widgets from remote values ────────────────

    # Suppress poll updates for channels changed within the last 10 seconds,
    # preventing the periodic check_remote_values from reverting user input
    # before program_manual has finished sending the new value.
    _RECENTLY_CHANGED_GUARD_S = 10.0

    def _update_ao_widgets(self, remote_values):
        """Update custom widgets when check_remote_values returns."""
        now = time.monotonic()
        for connection, value in remote_values.items():
            # Skip channels the user just changed — prevents poll reverting toggles
            if connection in self._recently_changed:
                if now - self._recently_changed[connection] < self._RECENTLY_CHANGED_GUARD_S:
                    continue
                del self._recently_changed[connection]

            value = float(value)

            # Update AO internal value (and voltage spinbox if applicable)
            if connection in self._AO:
                self._AO[connection].set_value(
                    value, program=False, update_gui=True
                )

            # Update toggle buttons
            if connection in self._toggle_buttons:
                is_on = value > 0.5
                btn = self._toggle_buttons[connection]
                btn.blockSignals(True)
                btn.setChecked(is_on)
                btn.blockSignals(False)
                self._style_toggle(connection, is_on)

            # Update combo boxes
            if connection in self._mode_combos:
                combo = self._mode_combos[connection]
                combo.blockSignals(True)
                combo.setCurrentIndex(int(value))
                combo.blockSignals(False)

        # Track lamps state from poll for mode combo interlocking
        # (done outside the skip-guard loop so interlocks always update)
        for connection, value in remote_values.items():
            m = _PREFIX_RE.match(connection)
            if m and m.group(2) == 'lamps':
                self._lamps_active[m.group(1)] = float(value) > 0.5
                self._update_mode_combos_enabled(m.group(1))

    # ── Mode combo interlocking ───────────────────────────────────────

    def _update_mode_combos_enabled(self, prefix):
        """Enable/disable mode combos based on lamp state, input enabled,
        and Keep Warm state. Mode changes require standby."""
        lamps_on = self._lamps_active.get(prefix, False)
        kw_on = self._keep_warm.get(prefix, False)
        for suffix in ('lamp_mode', 'qswitch_mode'):
            conn = f"{prefix}_{suffix}"
            if conn in self._mode_combos:
                self._mode_combos[conn].setEnabled(
                    self._input_enabled and not lamps_on and not kw_on
                )

    # ── Override: update monitors from PUB-SUB ────────────────────────

    def _on_monitor_value_received(self, connection, value_str):
        """Update custom monitor widgets from PUB-SUB values."""
        try:
            value = float(value_str)
        except (ValueError, TypeError):
            return

        # Per-laser disconnect detection: update timestamp, restore if offline
        m = _PREFIX_RE.match(connection)
        if m:
            prefix = m.group(1)
            self._last_monitor_time[prefix] = time.monotonic()
            if not self._laser_online.get(prefix, False):
                self._laser_online[prefix] = True
                if prefix in self._laser_groups:
                    self._laser_groups[prefix].setEnabled(True)
                    self._laser_groups[prefix].setTitle(prefix)

        # Temperature monitor
        if connection in self._temp_labels:
            self._style_temp(self._temp_labels[connection], value)
            # Evaluate Auto Keep Warm (prefix was extracted above at line 644)
            if m:
                self._evaluate_keep_warm(prefix, value)
            return

        # Voltage monitor
        if connection in self._voltage_labels:
            self._voltage_labels[connection].setText(f"(monitor: {int(value)} V)")
            return

        # Binary monitor indicators
        if connection in self._monitor_labels:
            self._style_monitor(connection, value)
            m = _PREFIX_RE.match(connection)
            if m:
                suffix = m.group(2)
                prefix = m.group(1)
                # Track lamps state for mode combo interlocking
                if suffix == 'lamps_monitor':
                    self._lamps_active[prefix] = value > 0.5
                    self._update_mode_combos_enabled(prefix)
                # Update action button colors on any binary monitor change
                if suffix in ('lamps_monitor', 'shutter_monitor', 'qswitch_monitor'):
                    self._update_action_button_state(prefix)
            return

        # Fallback: update AO object if it exists (e.g. standard AM widgets)
        if connection in self._AO:
            try:
                self._AO[connection].set_value(value, program=False, update_gui=True)
            except (ValueError, KeyError):
                pass

    # ── Per-laser health check ─────────────────────────────────────────

    def _check_laser_health(self):
        """Gray out lasers whose PUB-SUB data is stale (>30s)."""
        now = time.monotonic()
        for prefix, group in self._laser_groups.items():
            last = self._last_monitor_time.get(prefix, 0)
            if last > 0 and (now - last) > 30.0:
                if self._laser_online.get(prefix, False):
                    self._laser_online[prefix] = False
                    group.setEnabled(False)
                    group.setTitle("%s (OFFLINE)" % prefix)

    # ── Override: enable/disable controls ──────────────────────────────

    def _set_ao_widgets_enabled(self, enabled):
        """Enable/disable all interactive controls."""
        self._input_enabled = enabled
        # Voltage spinbox
        for widget in self.AO_widgets.values():
            widget.setEnabled(enabled)
        # Auto checkbox buttons
        for btn in self._keep_warm_buttons.values():
            btn.setEnabled(enabled)
        for btn in self._keep_warm_temp_buttons.values():
            btn.setEnabled(enabled)
        # Toggle buttons: respect keep_warm interlock
        for conn, btn in self._toggle_buttons.items():
            m = _PREFIX_RE.match(conn)
            if m:
                kw_on = self._keep_warm.get(m.group(1), False)
                btn.setEnabled(enabled and not kw_on)
            else:
                btn.setEnabled(enabled)
        # Mode combos: respect input-enabled, lamps-active, AND keep_warm
        for conn, combo in self._mode_combos.items():
            m = _PREFIX_RE.match(conn)
            if m:
                prefix = m.group(1)
                lamps_on = self._lamps_active.get(prefix, False)
                kw_on = self._keep_warm.get(prefix, False)
                combo.setEnabled(enabled and not lamps_on and not kw_on)
            else:
                combo.setEnabled(enabled)

    # ── Persistence ──────────────────────────────────────────────────

    def get_save_data(self):
        return {
            'keep_warm': dict(self._keep_warm),
            'keep_warm_temp': dict(self._keep_warm_temp),
        }

    def restore_save_data(self, data):
        saved_kw = data.get('keep_warm', {})
        for prefix, state in saved_kw.items():
            if prefix in self._keep_warm_buttons:
                self._keep_warm[prefix] = state
                cb = self._keep_warm_buttons[prefix]
                cb.blockSignals(True)
                cb.setChecked(state)
                cb.blockSignals(False)
                self._update_keep_warm_interlocks(prefix)
        # Support both old key ('auto_warmup_cold') and new key ('keep_warm_temp')
        saved_kwt = data.get('keep_warm_temp', data.get('auto_warmup_cold', {}))
        for prefix, state in saved_kwt.items():
            if prefix in self._keep_warm_temp_buttons:
                self._keep_warm_temp[prefix] = state
                self._warmup_triggered[prefix] = False
                cb = self._keep_warm_temp_buttons[prefix]
                cb.blockSignals(True)
                cb.setChecked(state)
                cb.blockSignals(False)
        # NOTE: Do NOT fire lamps here — worker doesn't exist yet.

    # ── Worker setup ──────────────────────────────────────────────────

    def initialise_workers(self):
        self.create_worker(
            "main_worker",
            "user_devices.BigSkyHub.blacs_workers.BigSkyWorker",
            {
                "mock": self.mock,
                "host": self.host,
                "port": self.reqrep_port,
                "child_output_connections": self.child_output_connections,
                "child_monitor_connections": self.child_monitor_connections,
                "keep_warm_state": dict(self._keep_warm),
            },
        )
        self.primary_worker = "main_worker"

        self._heartbeat_thread = None
        self._subscriber_thread = None
        self._pubsub_stop_event = threading.Event()
        self._pubsub_context = zmq.Context()

        if self.mock:
            self.reqrep_connected = True
            self.pubsub_connected = True
            self._fetch_initial_values()
            self._start_polling()
        else:
            self.connect_to_remote()

    def close_tab(self, finalise=True):
        self._laserHealthTimer.stop()
        return super().close_tab(finalise=finalise)
