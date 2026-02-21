from qtutils.qt import QtWidgets, QtCore
from qtutils import inmain

from blacs.device_base_class import define_state, MODE_MANUAL

from user_devices.RemoteControl.blacs_tabs import RemoteControlTab

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

    def initialise_GUI(self):
        super().initialise_GUI()

        # ── Raster Mode checkbox ──
        self.raster_check_box = QtWidgets.QCheckBox("Raster Mode (advance per shot)")
        self.main_gui_layout.addWidget(self.raster_check_box)
        self.raster_check_box.toggled.connect(self.on_raster_toggled)

        # ── Status indicators panel ──
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
        self.main_gui_layout.addWidget(status_frame)

        # Signal bridge for status topics
        self._status_bridge = _StatusSignalBridge()
        self._status_bridge.status_received.connect(self._on_status_received)

    # ── Worker setup ─────────────────────────────────────────────────

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

        # PUB-SUB thread handles
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
        """
        Subscribe to monitor connections AND status topics, routing
        each to the appropriate signal bridge.
        """
        stop = self._pubsub_stop_event
        subscribers = {}
        poller = zmq.Poller()

        try:
            # Subscribe to monitor connections (position values)
            for connection in self.child_monitor_connections:
                sub = self._pubsub_context.socket(zmq.SUB)
                sub.setsockopt(zmq.LINGER, 0)
                sub.connect(f"tcp://{self.host}:{self.pubsub_port}")
                sub.setsockopt_string(zmq.SUBSCRIBE, connection)
                subscribers[connection] = sub
                poller.register(sub, zmq.POLLIN)

            # Subscribe to status topics
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
