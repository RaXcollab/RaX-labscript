from qtutils.qt import QtWidgets, QtCore
from qtutils import inmain

from blacs.device_base_class import define_state, MODE_MANUAL

from user_devices.RemoteControl.blacs_tabs import (
    RemoteControlTab,
    DynamicStackedWidget,
    FailureButton,
    _PubSubSignalBridge,
)

import threading
import zmq


# ── Status signal bridge for PUB-SUB status topics ───────────────────

class _StatusSignalBridge(QtCore.QObject):
    """Emitted by the subscriber thread for non-monitor PUB-SUB topics."""
    status_received = QtCore.pyqtSignal(str, str)  # (topic, value)


# ── Colored status indicator widget ──────────────────────────────────

class StatusIndicator(QtWidgets.QFrame):
    """Small colored badge with a text label."""

    _COLORS = {
        "green": "#4CAF50",
        "yellow": "#FFC107",
        "red": "#f44336",
        "gray": "#9E9E9E",
    }

    def __init__(self, label_text="", color="gray", parent=None):
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)

        self._dot = QtWidgets.QLabel()
        self._dot.setFixedSize(12, 12)

        self._label = QtWidgets.QLabel(label_text)
        self._label.setStyleSheet("font-size: 11px;")

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        layout.addWidget(self._dot)
        layout.addWidget(self._label)
        layout.addStretch()
        self.setLayout(layout)

        self.set_color(color)

    def set_color(self, color):
        hex_color = self._COLORS.get(color, color)
        self._dot.setStyleSheet(
            f"background-color: {hex_color}; border-radius: 6px; border: 1px solid #666;"
        )

    def set_text(self, text):
        self._label.setText(text)

    def update_status(self, text, color):
        self.set_text(text)
        self.set_color(color)


# ── Main Tab ─────────────────────────────────────────────────────────

# Status topics that the subscriber should listen for (beyond monitor connections)
STATUS_TOPICS = ["raster_mode", "calibration_status", "raster_progress"]


class RasteringTab(RemoteControlTab):

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

        # PUB-SUB monitor cache: shared with worker for shot snapshots.
        # Updated at ~4 Hz by the subscriber thread. Worker reads from
        # this instead of making REQ-REP CHECK_VALUE round-trips.
        self._pubsub_monitor_cache = {}

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

        # ── 4. Create AO objects for all channels ──
        AO_prop = {}
        for dev in self.child_output_devices:
            cp = dev._properties
            lo, hi = cp["limits"]
            AO_prop[dev.parent_port] = {
                'base_unit': cp["units"],
                'min': lo, 'max': hi,
                'step': cp["step_size"],
                'decimals': cp["decimals"],
            }
        self.create_analog_outputs(AO_prop)

        AM_prop = {}
        self._monitor_format = {}  # {connection: (decimals, units)}
        for dev in self.child_monitor_devices:
            cp = dev._properties
            lo, hi = cp["limits"]
            AM_prop[dev.parent_port] = {
                'base_unit': cp["units"],
                'min': lo, 'max': hi,
                'step': cp["step_size"],
                'decimals': cp["decimals"],
            }
            self._monitor_format[dev.parent_port] = (cp["decimals"], cp["units"])
        self.create_analog_outputs(AM_prop)

        # ── 5. Create spinbox widgets for outputs only ──
        self.AO_widgets = self.create_analog_widgets(
            {conn: {} for conn in self.child_output_connections}
        )
        self.AM_widgets = {}

        # ── 6. Build paired position layout ──
        self._monitor_labels = {}  # {monitor_connection: QLabel}

        # Pair outputs with monitors by name convention (output + "_monitor")
        monitor_ports = {dev.parent_port: dev for dev in self.child_monitor_devices}

        position_group = QtWidgets.QGroupBox("Position")
        position_layout = QtWidgets.QVBoxLayout()
        position_layout.setContentsMargins(6, 6, 6, 6)
        position_layout.setSpacing(4)

        for out_dev in sorted(self.child_output_devices, key=lambda d: d.parent_port):
            conn = out_dev.parent_port
            mon_conn = f"{conn}_monitor"

            # Extract axis label: "Raster_X" → "X"
            axis = out_dev.name.split('_')[-1]

            row = QtWidgets.QHBoxLayout()
            row.setSpacing(8)

            axis_label = QtWidgets.QLabel(f"{axis}:")
            axis_label.setStyleSheet("font-weight: bold; min-width: 20px;")
            row.addWidget(axis_label)

            if conn in self.AO_widgets:
                row.addWidget(self.AO_widgets[conn])

            mon_decimals, mon_units = self._monitor_format.get(mon_conn, (4, "mm"))
            monitor_label = QtWidgets.QLabel(f"(monitor: -- {mon_units})")
            monitor_label.setStyleSheet("color: #666; padding-left: 8px;")
            self._monitor_labels[mon_conn] = monitor_label
            row.addWidget(monitor_label)
            row.addStretch()

            position_layout.addLayout(row)

        position_group.setLayout(position_layout)

        # ── 7. Raster Mode checkbox ──
        self.raster_check_box = QtWidgets.QCheckBox("Raster Mode (advance per shot)")

        # ── 8. Status indicators panel ──
        status_frame = QtWidgets.QFrame()
        status_layout = QtWidgets.QHBoxLayout()
        status_layout.setContentsMargins(4, 4, 4, 4)
        status_layout.setSpacing(12)

        self.raster_mode_indicator = StatusIndicator("Raster: —", "gray")
        self.calibration_indicator = StatusIndicator("Cal: —", "gray")
        self.progress_indicator = StatusIndicator("Progress: —", "gray")

        status_layout.addWidget(self.raster_mode_indicator)
        status_layout.addWidget(self.calibration_indicator)
        status_layout.addWidget(self.progress_indicator)
        status_layout.addStretch()
        status_frame.setLayout(status_layout)

        # Status signal bridge
        self._status_bridge = _StatusSignalBridge()
        self._status_bridge.status_received.connect(self._on_status_received)

        # ── 9. Assemble custom content widget ──
        self._position_widget = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout()
        content_layout.setContentsMargins(2, 2, 2, 2)
        content_layout.setSpacing(4)
        content_layout.addWidget(position_group)
        content_layout.addWidget(self.raster_check_box)
        content_layout.addWidget(status_frame)
        self._position_widget.setLayout(content_layout)

        self.raster_check_box.toggled.connect(self.on_raster_toggled)

        # ── 10. Reconnect buttons ──
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

        # ── 11. Layout assembly ──
        self.main_gui_layout = self.get_tab_layout()

        self.ao_placeholder = DynamicStackedWidget()
        self.ao_placeholder.addWidget(self._position_widget)
        self.ao_placeholder.addWidget(self.reconnect_reqrep_button)

        self._am_dummy = QtWidgets.QWidget()
        self.am_placeholder = DynamicStackedWidget()
        self.am_placeholder.addWidget(self._am_dummy)
        self.am_placeholder.addWidget(self.reconnect_pubsub_button)

        self.ao_toolpalette_widget = self._position_widget
        self.am_toolpalette_widget = self._am_dummy

        self.main_gui_layout.insertWidget(0, self.ao_placeholder)
        self.main_gui_layout.insertWidget(1, self.am_placeholder)

        # ── 12. Disable Input checkbox ──
        self.comms_check_box = QtWidgets.QCheckBox("Disable Input")
        self.main_gui_layout.addWidget(self.comms_check_box)
        self.comms_check_box.toggled.connect(self.on_checkbox_toggled)

        # ── 13. Initially hidden ──
        self.ao_placeholder.hide()
        self.am_placeholder.hide()
        self.comms_check_box.hide()

        # ── 14. Failure button ──
        self.failed_button = FailureButton()
        self.failed_button.connect_clicked(lambda: self.connect_to_remote())
        self.main_gui_layout.addWidget(self.failed_button)
        self.failed_button.hide()

    # ── Override: update AO widgets from remote values ────────────────

    def _update_ao_widgets(self, remote_values):
        """Update setpoint spinboxes from poll."""
        for connection, value in remote_values.items():
            value = float(value)
            if connection in self._AO:
                self._AO[connection].set_value(
                    value, program=False, update_gui=True
                )

    # ── Override: update monitors from PUB-SUB ────────────────────────

    def _on_monitor_value_received(self, connection, value_str):
        """Update monitor labels and PUB-SUB cache with position values."""
        try:
            value = float(value_str)
        except (ValueError, TypeError):
            return

        self._pubsub_monitor_cache[connection] = value

        if connection in self._monitor_labels:
            decimals, units = self._monitor_format.get(connection, (4, "mm"))
            self._monitor_labels[connection].setText(
                f"(monitor: {value:.{decimals}f} {units})"
            )

    # ── Override: enable/disable controls ──────────────────────────────

    def _set_ao_widgets_enabled(self, enabled):
        """Enable/disable setpoint spinboxes only."""
        for widget in self.AO_widgets.values():
            widget.setEnabled(enabled)

    # ── Worker setup ──────────────────────────────────────────────────

    def initialise_workers(self):
        self.create_worker(
            "main_worker",
            "user_devices.RasteringDevice.blacs_workers.RasteringWorker",
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

    # ── Raster checkbox ──────────────────────────────────────────────

    @define_state(MODE_MANUAL, True)
    def on_raster_toggled(self, state):
        yield (
            self.queue_work(
                self.primary_worker, 'update_raster_mode', raster_mode=state
            )
        )

    # ── Extended PUB-SUB subscriber (overrides parent) ───────────────

    def _subscriber_loop(self):
        """Subscribe to monitor connections AND status topics."""
        stop = self._pubsub_stop_event
        subscribers = {}
        poller = zmq.Poller()

        try:
            for connection in self.child_monitor_connections:
                sub = self._pubsub_context.socket(zmq.SUB)
                sub.setsockopt(zmq.LINGER, 0)
                sub.connect(f"tcp://{self.host}:{self.pubsub_port}")
                sub.setsockopt_string(zmq.SUBSCRIBE, connection)
                subscribers[connection] = sub
                poller.register(sub, zmq.POLLIN)

            for topic in STATUS_TOPICS:
                sub = self._pubsub_context.socket(zmq.SUB)
                sub.setsockopt(zmq.LINGER, 0)
                sub.connect(f"tcp://{self.host}:{self.pubsub_port}")
                sub.setsockopt_string(zmq.SUBSCRIBE, topic)
                subscribers[topic] = sub
                poller.register(sub, zmq.POLLIN)

            while self.pubsub_connected and not stop.is_set():
                socks = dict(poller.poll(timeout=500))
                for sub_sock in socks:
                    try:
                        message = sub_sock.recv_string(zmq.NOBLOCK)
                        parts = message.split(" ", 1)
                        if len(parts) == 2:
                            topic, val = parts
                            if topic in STATUS_TOPICS:
                                self._status_bridge.status_received.emit(
                                    topic, val
                                )
                            else:
                                self._pubsub_bridge.monitor_value_received.emit(
                                    topic, val
                                )
                    except zmq.ZMQError:
                        pass

        except Exception as e:
            self.logger.error(f"Subscriber loop error: {e}")
        finally:
            for sub in subscribers.values():
                try:
                    sub.close()
                except Exception:
                    pass

    # ── Status signal handler (runs on GUI thread) ───────────────────

    def _on_status_received(self, topic, value):
        """Update colored indicators based on PUB-SUB status messages."""
        if topic == "raster_mode":
            mode_map = {
                "idle": ("Raster: Idle", "gray"),
                "manual": ("Raster: Manual", "gray"),
                "step": ("Raster: Step", "green"),
                "continuous": ("Raster: Continuous", "yellow"),
            }
            text, color = mode_map.get(value, (f"Raster: {value}", "gray"))
            self.raster_mode_indicator.update_status(text, color)

        elif topic == "calibration_status":
            if value == "calibrated":
                self.calibration_indicator.update_status("Cal: OK", "green")
            else:
                self.calibration_indicator.update_status("Cal: None", "red")

        elif topic == "raster_progress":
            self.progress_indicator.set_text(f"Progress: {value}")
