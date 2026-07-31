from qtutils.qt import QtWidgets, QtGui, QtCore
from qtutils import inmain

from blacs.device_base_class import (
    DeviceTab,
    define_state,
    MODE_BUFFERED,
    MODE_MANUAL,
    MODE_TRANSITION_TO_BUFFERED,
    MODE_TRANSITION_TO_MANUAL,
)

import threading
import zmq
import time

from labscript_utils.ls_zprocess import ProcessTree, Event

# Ensure the BLACS-internal EventBroker is up before any worker subprocess
# spawns. check_broker() is idempotent (guards on broker_in_port is None),
# so this is safe to call from module-top across multiple import sites
# (LaserLock/BigSky/Rastering all import this module).
ProcessTree.instance().check_broker()


# ── Helper widgets ───────────────────────────────────────────────────

class DynamicStackedWidget(QtWidgets.QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(self.adjustSize)

    def sizeHint(self):
        if self.currentWidget():
            return self.currentWidget().sizeHint()
        return super().sizeHint()

    def minimumSizeHint(self):
        if self.currentWidget():
            return self.currentWidget().minimumSizeHint()
        return super().minimumSizeHint()

    def adjustSize(self):
        hint = self.minimumSizeHint()
        if hint.isValid():
            self.setMinimumSize(hint)
        super().adjustSize()
        if self.parent() and isinstance(self.parent(), QtWidgets.QWidget):
            self.parent().adjustSize()


class FailureButton(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.button = QtWidgets.QPushButton("CONNECTION FAILED, CLICK TO RECONNECT")
        self.button.setStyleSheet("""
            QPushButton {
                color: white;
                font-weight: bold;
                background-color: #ff6666;
                border: 2px solid #ff4d4d;
                border-radius: 10px;
                padding: 20px 40px;
                font-size: 18px;
            }
            QPushButton:hover { background-color: #ff4d4d; }
            QPushButton:pressed { background-color: #ff3333; }
        """)

        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(QtCore.Qt.AlignCenter)
        layout.addStretch(1)
        layout.addWidget(self.button, alignment=QtCore.Qt.AlignCenter)
        layout.addStretch(1)
        self.setLayout(layout)

    def connect_clicked(self, slot):
        self.button.clicked.connect(slot)


# ── Signal bridge for thread-safe GUI updates from subscriber threads ──

class _PubSubSignalBridge(QtCore.QObject):
    """
    Background subscriber threads emit these signals; the tab connects
    slots that run on the main (GUI) thread via auto-connection.
    """
    pubsub_status_changed = QtCore.pyqtSignal(bool)     # connected True/False
    monitor_value_received = QtCore.pyqtSignal(str, str) # connection, value


# ── Main Tab ─────────────────────────────────────────────────────────

class RemoteControlTab(DeviceTab):

    def __init__(self, *args, **kwargs):
        # Subscriber-registry + monitor-cache attributes MUST exist before
        # DeviceTab.__init__ runs initialise_GUI: subclasses override
        # initialise_GUI without super() and call _register_subscriber
        # (RasteringTab), and the inherited _subscriber_loop daemon reads
        # _extra_topics as its second statement. Missing attrs here is the
        # 2026-05-26 rollback failure class. Tested in
        # tests/test_tab_registry.py.
        self._init_subscriber_registry()
        super().__init__(*args, **kwargs)

    def _init_subscriber_registry(self):
        """Idempotent init of subscriber-registry state (pure python)."""
        self._pubsub_monitor_cache = {}
        self._extra_topics = {}
        self._subscriber_thread = None

    def initialise_GUI(self):
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
        # Updated at ~4 Hz by the subscriber thread. Worker reads from this
        # for initial/final monitor values instead of issuing REQ-REP
        # CHECK_VALUE round-trips during transition_to_buffered/post_experiment.
        self._pubsub_monitor_cache = {}

        # Extra subscriber topic registry: subclasses call
        # _register_subscriber() during initialise_GUI to subscribe to status
        # topics (etc.) beyond child_monitor_connections. Frozen at thread
        # start via local snapshot in _subscriber_loop — must not be mutated
        # after connect_to_pubsub() runs.
        self._extra_topics = {}

        # Signal bridge for thread-safe GUI updates from subscriber threads
        self._pubsub_bridge = _PubSubSignalBridge()
        self._pubsub_bridge.pubsub_status_changed.connect(self._on_pubsub_status_changed)
        self._pubsub_bridge.monitor_value_received.connect(self._on_monitor_value_received)

        # ── Discover child devices ──
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

        # ── Analog Output widgets (read/write) ──
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
        _, self.AO_widgets, _ = self.auto_create_widgets()
        self.ao_toolpalette_widget = self.auto_place_widgets(
            ("Analog Outputs", self.AO_widgets)
        )

        # ── Analog Monitor widgets (read-only) ──
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
        _, self.AM_widgets, _ = self.create_subset_widgets(AM_prop)
        self.am_toolpalette_widget = self.auto_place_widgets(
            ("Analog Monitors", self.AM_widgets)
        )
        for _, widget in self.AM_widgets.items():
            widget.setEnabled(False)

        # ── Reconnect buttons ──
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

        # ── Layout ──
        self.main_gui_layout = self.get_tab_layout()

        self.ao_placeholder = DynamicStackedWidget()
        self.am_placeholder = DynamicStackedWidget()

        self.ao_placeholder.addWidget(self.ao_toolpalette_widget)
        self.ao_placeholder.addWidget(self.reconnect_reqrep_button)
        self.am_placeholder.addWidget(self.am_toolpalette_widget)
        self.am_placeholder.addWidget(self.reconnect_pubsub_button)

        self.main_gui_layout.insertWidget(0, self.ao_placeholder)
        self.main_gui_layout.insertWidget(1, self.am_placeholder)

        # EnableComms checkbox
        self.comms_check_box = QtWidgets.QCheckBox("Disable Input")
        self.main_gui_layout.addWidget(self.comms_check_box)
        self.comms_check_box.toggled.connect(self.on_checkbox_toggled)

        # Hide everything until connection is established
        self.ao_placeholder.hide()
        self.am_placeholder.hide()
        self.comms_check_box.hide()

        # Connection-failed button
        self.failed_button = FailureButton()
        self.failed_button.connect_clicked(lambda: self.connect_to_remote())
        self.main_gui_layout.addWidget(self.failed_button)
        self.failed_button.hide()

    # ── Worker setup ─────────────────────────────────────────────────

    def initialise_workers(self):
        self.create_worker(
            "main_worker",
            "user_devices.RemoteControl.blacs_workers.RemoteControlWorker",
            {
                "mock": self.mock,
                # Connection-table property; becomes self.wait_for_lock in the
                # worker (read at transition_to_buffered). Without this line
                # the knob is dead and buffered shots never wait for lock.
                "wait_for_lock": self.properties.get("wait_for_lock", False),
                "host": self.host,
                "port": self.reqrep_port,
                "child_output_connections": self.child_output_connections,
                "child_monitor_connections": self.child_monitor_connections,
            },
        )
        self.primary_worker = "main_worker"

        # Subscriber thread handles — used to avoid duplicate threads
        self._heartbeat_thread = None
        self._subscriber_thread = None
        self._pubsub_stop_event = threading.Event()
        self._pubsub_context = zmq.Context()

        if self.mock:
            self.reqrep_connected = True
            self._fetch_initial_values()
            self._start_polling()
        else:
            self.connect_to_remote()

    # ── Connection ───────────────────────────────────────────────────

    def connect_to_remote(self):
        self.connect_to_reqrep()
        self._deferred_pubsub_connect()

    @define_state(MODE_MANUAL, True)
    def _deferred_pubsub_connect(self):
        """Start PubSub threads only after the state machine mainloop is running."""
        self.connect_to_pubsub()

    @define_state(MODE_MANUAL, True)
    def connect_to_reqrep(self):
        self.reqrep_connected = yield (
            self.queue_work(self.primary_worker, 'connect_to_remote')
        )
        inmain(self._update_gui_status)
        if self.reqrep_connected:
            # Fetch initial values as a separate state machine event
            # so this generator only has one yield.
            self._fetch_initial_values()

    @define_state(MODE_MANUAL, True)
    def _fetch_initial_values(self):
        """Pull current setpoints from the server so the front panel
        reflects actual values instead of starting at 0."""
        remote_values = yield (
            self.queue_work(self.primary_worker, 'check_remote_values')
        )
        if remote_values:
            self.logger.info(f"Fetched initial setpoints: {remote_values}")
            inmain(self._update_ao_widgets, remote_values)
        else:
            self.logger.warning("Failed to fetch initial setpoints from remote server")
        self._mark_initial_fetch_done()

    @define_state(MODE_MANUAL, True)
    def _mark_initial_fetch_done(self):
        """Allow program_manual to send values now that we have real setpoints."""
        yield (self.queue_work(self.primary_worker, 'mark_initial_fetch_done'))

    def reconnect_reqrep(self):
        self.connect_to_reqrep()

    def reconnect_pubsub(self):
        self.connect_to_pubsub()

    def connect_to_pubsub(self):
        """Start (or restart) the heartbeat subscriber thread."""
        # Lazy-create the post-side Event ONCE per tab lifetime. The internal
        # EventBroker lives in the BLACS root process and only dies with BLACS,
        # so there is no legitimate reason to recreate the post Event on
        # reconnect. The hasattr guard is required: connecting the same Qt
        # slot twice causes duplicate fires (verified Test 4 T3.4).
        if not hasattr(self, '_monitor_event'):
            self._monitor_event = Event(
                f'{self.device_name}_pubsub_monitor',
                role='post',
            )
            self._pubsub_bridge.monitor_value_received.connect(
                self._post_to_internal_broker
            )

        # Signal any existing threads to stop
        self._pubsub_stop_event.set()
        time.sleep(0.05)  # give them a moment
        self._pubsub_stop_event.clear()
        self.pubsub_connected = False

        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_subscriber_loop, daemon=True
        )
        self._heartbeat_thread.start()

    # ── Polling setup ────────────────────────────────────────────────

    def _start_polling(self):
        """Begin periodic remote-value checks (called after connection)."""
        self.statemachine_timeout_add(5000, self.check_remote_values)

    # ── Periodic remote-value check (runs in BLACS state machine) ────

    @define_state(
        MODE_MANUAL | MODE_BUFFERED | MODE_TRANSITION_TO_BUFFERED | MODE_TRANSITION_TO_MANUAL,
        True,
    )
    def check_remote_values(self):
        """
        Periodically poll OUTPUT setpoints from the remote server via REQ-REP.
        Updates the front-panel widgets to reflect any changes made on the
        remote GUI side.
        """
        remote_values = yield (
            self.queue_work(self.primary_worker, 'check_remote_values')
        )
        if remote_values:
            inmain(self._update_ao_widgets, remote_values)

    def _update_ao_widgets(self, remote_values):
        """Update AO front-panel widgets. Runs on GUI thread via inmain()."""
        for connection, value in remote_values.items():
            if connection in self.AO_widgets:
                self._AO[connection].set_value(
                    float(value), program=False, update_gui=True
                )

    @define_state(
        MODE_MANUAL | MODE_BUFFERED | MODE_TRANSITION_TO_BUFFERED | MODE_TRANSITION_TO_MANUAL,
        True,
    )
    def status_monitor(self):
        """Poll MONITOR values via REQ-REP (legacy — kept for compatibility)."""
        response = yield (
            self.queue_work(self.primary_worker, "check_status")
        )
        if response:
            inmain(self._update_monitor_widgets, response)

    def _update_monitor_widgets(self, response):
        """Update monitor front-panel widgets. Runs on GUI thread via inmain()."""
        for connection, value in response.items():
            if connection in self.AM_widgets:
                self._AO[connection].set_value(
                    float(value), program=False, update_gui=True
                )

    # ── Checkbox toggle ──────────────────────────────────────────────

    @define_state(MODE_MANUAL, True)
    def on_checkbox_toggled(self, state):
        inmain(self._set_ao_widgets_enabled, not state)

        # Adjust polling rate: faster when comms disabled (remote may change freely)
        self.statemachine_timeout_remove(self.check_remote_values)
        if state:
            self.statemachine_timeout_add(500, self.check_remote_values)
        else:
            self.statemachine_timeout_add(5000, self.check_remote_values)

        yield (
            self.queue_work(self.primary_worker, 'update_settings', enable_comms=not state)
        )

    def _set_ao_widgets_enabled(self, enabled):
        """Enable/disable AO widgets. Runs on GUI thread via inmain()."""
        for widget in self.AO_widgets.values():
            widget.setEnabled(enabled)

    # ── PUB-SUB: heartbeat subscriber (background thread) ───────────

    def _heartbeat_subscriber_loop(self):
        """
        Runs in a daemon thread.  Subscribes to "heartbeat" topic.
        On first heartbeat -> sets pubsub_connected, starts data subscriber.
        On missed heartbeat -> sets pubsub_connected=False, retries after backoff.

        The outer while loop ensures automatic reconnection if the server
        goes down and comes back.
        """
        stop = self._pubsub_stop_event

        while not stop.is_set():
            sock = self._pubsub_context.socket(zmq.SUB)
            sock.setsockopt(zmq.LINGER, 0)
            sock.connect(f"tcp://{self.host}:{self.pubsub_port}")
            sock.setsockopt_string(zmq.SUBSCRIBE, "heartbeat")

            poller = zmq.Poller()
            poller.register(sock, zmq.POLLIN)

            try:
                while not stop.is_set():
                    socks = dict(poller.poll(5000))  # 5 s timeout
                    if sock in socks:
                        msg = sock.recv_string(zmq.NOBLOCK)
                        if msg == "heartbeat" and not self.pubsub_connected:
                            self.pubsub_connected = True
                            self._pubsub_bridge.pubsub_status_changed.emit(True)
                            self.logger.debug("PUB-SUB heartbeat detected — connected")
                            self._start_subscriber()
                    else:
                        # Missed heartbeat
                        if self.pubsub_connected:
                            self.pubsub_connected = False
                            self._pubsub_bridge.pubsub_status_changed.emit(False)
                            self.logger.warning("PUB-SUB heartbeat timeout — disconnected")
                        break  # break inner loop -> outer loop retries
            except zmq.ZMQError as e:
                self.logger.error(f"Heartbeat subscriber ZMQ error: {e}")
                if self.pubsub_connected:
                    self.pubsub_connected = False
                    self._pubsub_bridge.pubsub_status_changed.emit(False)
            finally:
                try:
                    sock.close()
                except Exception:
                    pass

            # Back off before retrying (unless told to stop)
            if not stop.is_set():
                stop.wait(2.0)

    # ── PUB-SUB: data subscriber (background thread) ────────────────

    def _start_subscriber(self):
        """Launch the data subscriber thread if not already running."""
        if self._subscriber_thread is not None and self._subscriber_thread.is_alive():
            return
        self._subscriber_thread = threading.Thread(
            target=self._subscriber_loop, daemon=True
        )
        self._subscriber_thread.start()

    def _register_subscriber(self, topic, signal_emit):
        """Register an extra ZMQ PUB topic to subscribe to.

        ``signal_emit(topic, value_str)`` is invoked from the subscriber
        daemon thread when a matching message arrives. Must be a bound
        ``pyqtSignal.emit`` (queued cross-thread dispatch) — do not call
        widgets directly from the callback.

        Call from ``initialise_GUI`` BEFORE ``connect_to_pubsub`` spawns
        the daemon. The subscriber loop snapshots ``self._extra_topics``
        once at thread start; mutations afterwards are ignored.

        Defensive guard: registering after the subscriber thread is alive
        is a silent footgun (the registration is accepted into the dict
        but never seen by the daemon's frozen ``extras`` snapshot). Raise
        ``RuntimeError`` to fail loudly instead.
        """
        if (self._subscriber_thread is not None
                and self._subscriber_thread.is_alive()):
            raise RuntimeError(
                "_register_subscriber(%r) called after subscriber thread "
                "started; the daemon snapshots the registry at thread "
                "start and will not see this topic. Register before "
                "connect_to_pubsub()." % topic)
        self._extra_topics[topic] = signal_emit

    def _subscriber_loop(self):
        """
        Subscribe to monitor connection topics + any topics registered
        via ``_register_subscriber()``, and dispatch values to the GUI
        via the appropriate signal (thread-safe).

        Frozen registry: ``self._extra_topics`` is snapshotted once at
        thread start (``extras``). Subclasses adding subscriptions after
        the loop has started will not see them — by design (daemon-thread
        mutability hazard).
        """
        stop = self._pubsub_stop_event
        extras = dict(self._extra_topics)  # frozen snapshot
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

            for topic in extras:
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
                            if topic in extras:
                                extras[topic](topic, val)
                            else:
                                self._pubsub_bridge.monitor_value_received.emit(topic, val)
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

    # ── Signal slots (run on GUI thread) ─────────────────────────────

    def _on_pubsub_status_changed(self, connected):
        """Called on the GUI thread when PUB-SUB connectivity changes."""
        self.pubsub_connected = connected
        self._update_gui_status()

    def _on_monitor_value_received(self, connection, value_str):
        """Called on the GUI thread when a PUB-SUB monitor value arrives."""
        try:
            value = float(value_str)
        except (ValueError, TypeError):
            return
        # Update shared PUB-SUB cache (worker reads for shot snapshots).
        self._pubsub_monitor_cache[connection] = value
        if connection in self.AM_widgets:
            try:
                self._AO[connection].set_value(
                    value, program=False, update_gui=True
                )
            except KeyError as e:
                self.logger.debug(f"Monitor update error for {connection}: {e}")

    def _post_to_internal_broker(self, connection, value_str):
        """Forward a PUB-SUB monitor value into the BLACS-internal
        EventBroker so worker subprocesses can subscribe.

        Runs on the GUI thread via Qt queued connection from the daemon
        subscriber thread that emits ``_pubsub_bridge.monitor_value_received``.

        Numeric-only contract: only values that float() parses are forwarded.
        If a future subclass needs to forward string-valued monitors, it
        must override this method. (Empirically all current devices are
        numeric: THz, V, A, deg C, raster coords.)
        """
        try:
            value = float(value_str)
        except (ValueError, TypeError):
            return  # non-numeric, silently dropped per contract
        try:
            self._monitor_event.post(connection, value)
        except Exception as e:
            # post() should not fail (PUSH is non-blocking, broker is local).
            # Log loudly if it does so we notice broken plumbing.
            self.logger.error(
                f"_post_to_internal_broker: post failed for "
                f"{connection}={value}: {type(e).__name__}: {e}"
            )

    # ── GUI status management ────────────────────────────────────────

    def _update_gui_status(self):
        """Show/hide widgets based on connectivity state.
        Must be called on the GUI thread (via inmain or Qt signal slot)."""
        reqrep = self.reqrep_connected
        pubsub = self.pubsub_connected

        if not reqrep and not pubsub:
            # Fully disconnected
            self.failed_button.show()
            self.ao_placeholder.hide()
            self.am_placeholder.hide()
            self.comms_check_box.hide()
            return

        # At least one connection — hide failure button, show placeholders
        self.failed_button.hide()
        self.ao_placeholder.show()
        self.am_placeholder.show()

        if reqrep and pubsub:
            # Fully connected
            self.ao_placeholder.setCurrentWidget(self.ao_toolpalette_widget)
            self.am_placeholder.setCurrentWidget(self.am_toolpalette_widget)
            self.comms_check_box.show()
            self._start_polling()

        elif reqrep:
            # REQ-REP only
            self.ao_placeholder.setCurrentWidget(self.ao_toolpalette_widget)
            self.am_placeholder.setCurrentWidget(self.reconnect_pubsub_button)
            self.comms_check_box.show()
            self._start_polling()

        elif pubsub:
            # PUB-SUB only
            self.ao_placeholder.setCurrentWidget(self.reconnect_reqrep_button)
            self.am_placeholder.setCurrentWidget(self.am_toolpalette_widget)
            self.comms_check_box.hide()

    def close_tab(self, finalise=True):
        """Stop PUB-SUB daemon threads before Qt objects are destroyed."""
        self._pubsub_stop_event.set()
        self.pubsub_connected = False

        THREAD_JOIN_TIMEOUT = 2.0
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=THREAD_JOIN_TIMEOUT)
        if self._subscriber_thread is not None and self._subscriber_thread.is_alive():
            self._subscriber_thread.join(timeout=THREAD_JOIN_TIMEOUT)

        try:
            self._pubsub_context.term()
        except Exception:
            pass

        return super().close_tab(finalise=finalise)
