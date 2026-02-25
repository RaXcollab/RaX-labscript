import threading

import zmq
from qtutils.qt import QtWidgets, QtCore
from qtutils import inmain

from blacs.device_base_class import define_state, MODE_MANUAL

from user_devices.RemoteControl.blacs_tabs import (
    RemoteControlTab,
    DynamicStackedWidget,
    FailureButton,
    _PubSubSignalBridge,
)

# Lock quality threshold: |error| < this → "Locked" (green)
_LOCK_THRESHOLD_MHZ = 100.0


class LaserLockTab(RemoteControlTab):
    """BLACS tab for wavemeter-locked lasers.

    Pairs each laser's frequency setpoint with its wavemeter reading,
    shows error in MHz, and provides a lock quality indicator.
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

        # ── 4. Create AO objects for outputs only ──
        # (monitors share connection IDs with outputs, so we skip AO creation
        #  for monitors to avoid overwriting output AOs in self._AO)
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

        # Create standard spinbox widgets for all outputs
        self.AO_widgets = self.create_analog_widgets(
            {conn: {} for conn in self.child_output_connections}
        )
        self.AM_widgets = {}

        # ── 5. Build paired laser group boxes ──
        self._monitor_labels = {}   # {connection_id: QLabel}
        self._error_labels = {}     # {connection_id: QLabel}
        self._lock_indicators = {}  # {connection_id: QLabel}

        # Pair outputs with monitors by shared connection ID
        monitor_by_port = {dev.parent_port: dev for dev in self.child_monitor_devices}
        self._pairs = []  # [(connection_id, output_dev, monitor_dev, display_name)]
        for dev in self.child_output_devices:
            mon_dev = monitor_by_port.get(dev.parent_port)
            # Extract display name: "Vexlum_Setpoint" → "Vexlum"
            display_name = dev.name.replace('_Setpoint', '').replace('_', ' ')
            self._pairs.append((dev.parent_port, dev, mon_dev, display_name))

        self._laser_widget = QtWidgets.QWidget()
        laser_layout = QtWidgets.QVBoxLayout()
        laser_layout.setContentsMargins(2, 2, 2, 2)
        laser_layout.setSpacing(4)
        self._laser_widget.setLayout(laser_layout)

        for conn_id, output_dev, monitor_dev, display_name in self._pairs:
            group = self._create_laser_group(conn_id, display_name)
            laser_layout.addWidget(group)

        # ── 6. Reconnect buttons ──
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

        # ── 7. Layout assembly ──
        self.main_gui_layout = self.get_tab_layout()

        self.ao_placeholder = DynamicStackedWidget()
        self.ao_placeholder.addWidget(self._laser_widget)
        self.ao_placeholder.addWidget(self.reconnect_reqrep_button)

        self._am_dummy = QtWidgets.QWidget()
        self.am_placeholder = DynamicStackedWidget()
        self.am_placeholder.addWidget(self._am_dummy)
        self.am_placeholder.addWidget(self.reconnect_pubsub_button)

        self.ao_toolpalette_widget = self._laser_widget
        self.am_toolpalette_widget = self._am_dummy

        self.main_gui_layout.insertWidget(0, self.ao_placeholder)
        self.main_gui_layout.insertWidget(1, self.am_placeholder)

        # ── 8. Disable Input checkbox ──
        self.comms_check_box = QtWidgets.QCheckBox("Disable Input")
        self.main_gui_layout.addWidget(self.comms_check_box)
        self.comms_check_box.toggled.connect(self.on_checkbox_toggled)

        # ── 9. Initially hidden ──
        self.ao_placeholder.hide()
        self.am_placeholder.hide()
        self.comms_check_box.hide()

        # ── 10. Failure button ──
        self.failed_button = FailureButton()
        self.failed_button.connect_clicked(lambda: self.connect_to_remote())
        self.main_gui_layout.addWidget(self.failed_button)
        self.failed_button.hide()

    # ── Per-laser group box builder ───────────────────────────────────

    def _create_laser_group(self, conn_id, display_name):
        """Build a QGroupBox with setpoint, wavemeter, error, and lock indicator."""
        group = QtWidgets.QGroupBox(display_name)
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # ── Setpoint row (standard AO spinbox) ──
        if conn_id in self.AO_widgets:
            setpoint_row = QtWidgets.QHBoxLayout()
            setpoint_label = QtWidgets.QLabel("Setpoint:")
            setpoint_label.setStyleSheet("font-weight: bold;")
            setpoint_row.addWidget(setpoint_label)
            setpoint_row.addWidget(self.AO_widgets[conn_id])
            setpoint_row.addStretch()
            layout.addLayout(setpoint_row)

        # ── Wavemeter + error row ──
        monitor_row = QtWidgets.QHBoxLayout()
        monitor_row.setSpacing(16)

        monitor_label = QtWidgets.QLabel("Wavemeter: -- THz")
        monitor_label.setStyleSheet("color: #666;")
        self._monitor_labels[conn_id] = monitor_label
        monitor_row.addWidget(monitor_label)

        error_label = QtWidgets.QLabel("Error: -- MHz")
        error_label.setStyleSheet("color: #999;")
        self._error_labels[conn_id] = error_label
        monitor_row.addWidget(error_label)

        monitor_row.addStretch()
        layout.addLayout(monitor_row)

        # ── Lock indicator ──
        lock_label = QtWidgets.QLabel("● --")
        lock_label.setStyleSheet("color: #999; font-weight: bold;")
        self._lock_indicators[conn_id] = lock_label
        layout.addWidget(lock_label)

        group.setLayout(layout)
        return group

    # ── Update error and lock indicator ───────────────────────────────

    def _update_error_display(self, conn_id, monitor_value):
        """Compute error and update error label + lock indicator."""
        if conn_id not in self._AO:
            return
        setpoint = self._AO[conn_id].value
        error_thz = monitor_value - setpoint
        error_mhz = error_thz * 1e6

        # Error label
        if conn_id in self._error_labels:
            self._error_labels[conn_id].setText(f"Error: {error_mhz:+.1f} MHz")
            if abs(error_mhz) < _LOCK_THRESHOLD_MHZ:
                self._error_labels[conn_id].setStyleSheet("color: #4CAF50;")
            else:
                self._error_labels[conn_id].setStyleSheet("color: #f44336;")

        # Lock indicator
        if conn_id in self._lock_indicators:
            if abs(error_mhz) < _LOCK_THRESHOLD_MHZ:
                self._lock_indicators[conn_id].setText("● Locked")
                self._lock_indicators[conn_id].setStyleSheet(
                    "color: #4CAF50; font-weight: bold;"
                )
            else:
                self._lock_indicators[conn_id].setText("● Unlocked")
                self._lock_indicators[conn_id].setStyleSheet(
                    "color: #f44336; font-weight: bold;"
                )

    # ── Override: compare remote vs saved on startup ──────────────────

    @define_state(MODE_MANUAL, True)
    def _fetch_initial_values(self):
        """Pull current setpoints from the server.  If they differ from
        the saved BLACS state (e.g. after a restart zeroed the remote GUI),
        prompt the user to choose which to keep."""
        remote_values = yield (
            self.queue_work(self.primary_worker, 'check_remote_values')
        )

        if not remote_values:
            self.logger.warning(
                "Failed to fetch initial setpoints from remote server"
            )
            self._mark_initial_fetch_done()
            return

        self.logger.info(f"Fetched initial setpoints: {remote_values}")

        # Build display-name lookup from _pairs (populated in initialise_GUI)
        display_names = {
            conn_id: display_name
            for conn_id, _, _, display_name in self._pairs
        }

        # Compare remote values with saved state already in self._AO[].value
        THRESHOLD = 1e-8  # THz  (~0.01 MHz, filters floating-point noise)
        mismatches = {}
        for connection, remote_val in remote_values.items():
            if connection not in self._AO:
                continue
            saved_val = self._AO[connection].value
            if abs(float(remote_val) - saved_val) > THRESHOLD:
                name = display_names.get(connection, str(connection))
                mismatches[connection] = (name, saved_val, float(remote_val))

        if not mismatches:
            # Values agree — accept remote silently (same as base class)
            inmain(self._update_ao_widgets, remote_values)
            self._mark_initial_fetch_done()
            return

        # Build dialog text
        lines = []
        for connection, (name, saved_val, remote_val) in mismatches.items():
            diff_mhz = (remote_val - saved_val) * 1e6
            lines.append(
                f"  {name}: saved {saved_val:.9f} THz, "
                f"remote {remote_val:.9f} THz "
                f"(\u0394 {diff_mhz:+.3f} MHz)"
            )
        detail = "\n".join(lines)
        msg = (
            "The remote laser lock GUI has different frequency setpoints "
            "than the saved BLACS state.\n"
            "This usually means the GUI restarted with zeroed values.\n\n"
            f"{detail}\n\n"
            "Use SAVED values (Yes) or accept REMOTE values (No)?"
        )

        answer = inmain(
            QtWidgets.QMessageBox.question,
            self._ui,
            "Setpoint Mismatch",
            msg,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes,
        )

        if answer == QtWidgets.QMessageBox.Yes:
            # Keep saved values; program them to the remote server
            self.logger.info("User chose SAVED values; will program to server")
            self._mark_initial_fetch_done()
            self.program_device()
        else:
            # Accept remote values; update front panel widgets
            self.logger.info("User chose REMOTE values; updating front panel")
            inmain(self._update_ao_widgets, remote_values)
            self._mark_initial_fetch_done()

    # ── Override: update AO widgets from remote values ────────────────

    def _update_ao_widgets(self, remote_values):
        """Update setpoint spinboxes and recompute error displays."""
        for connection, value in remote_values.items():
            value = float(value)
            if connection in self._AO:
                self._AO[connection].set_value(
                    value, program=False, update_gui=True
                )

    # ── Override: update monitors from PUB-SUB ────────────────────────

    def _on_monitor_value_received(self, connection, value_str):
        """Update wavemeter label and error/lock display."""
        try:
            value = float(value_str)
        except (ValueError, TypeError):
            return

        # Update wavemeter label
        if connection in self._monitor_labels:
            self._monitor_labels[connection].setText(f"Wavemeter: {value:.9f} THz")
            self._update_error_display(connection, value)

    # ── Override: enable/disable controls ──────────────────────────────

    def _set_ao_widgets_enabled(self, enabled):
        """Enable/disable setpoint spinboxes only."""
        for widget in self.AO_widgets.values():
            widget.setEnabled(enabled)

    # ── Worker setup ──────────────────────────────────────────────────

    def initialise_workers(self):
        self.create_worker(
            "main_worker",
            "user_devices.RemoteControl.blacs_workers.RemoteControlWorker",
            {
                "mock": self.mock,
                "host": self.host,
                "port": self.reqrep_port,
                "child_output_connections": self.child_output_connections,
                "child_monitor_connections": self.child_monitor_connections,
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
