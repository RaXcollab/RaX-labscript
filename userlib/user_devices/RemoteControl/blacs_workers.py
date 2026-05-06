import time
import threading
import pickle

from blacs.tab_base_classes import Worker
import numpy as np
import labscript_utils.h5_lock
import h5py
import zmq
import json

from labscript_utils.ls_zprocess import Event

# PUB-SUB monitor cache constants (see design spec Tasks 1, 2, 3, 6).
PUBSUB_DRAIN_POLL_TIMEOUT_MS = 500   # max idle shutdown latency
PUBSUB_SHUTDOWN_JOIN_TIMEOUT = 1.0   # seconds; daemon=True is the safety net


# Default timeouts (ms)
DEFAULT_TIMEOUT_MS = 5000        # General REQ-REP operations (HELLO, CHECK_VALUE, manual programs)
PROGRAM_TIMEOUT_MS = 120_000     # PROGRAM_VALUE with wait_for_lock — server may block up to 60s


class RemoteCommunication:
    """
    ZMQ REQ-REP communication with a remote device server.

    JSON Protocol:
    ──────────────
    Request:  {"action": str, "connection": str, "value": any, "wait_for_lock": bool}
    Response: {"status": "SUCCESS"|"ERROR", "message": str, "value": any}

    Actions: "HELLO", "PROGRAM_VALUE", "CHECK_VALUE"
    """

    def __init__(self, host=None, port=None, logger=None, child_connections=None,
                 mock=False, timeout_ms=DEFAULT_TIMEOUT_MS,
                 program_timeout_ms=PROGRAM_TIMEOUT_MS):
        self.mock = mock
        self.logger = logger
        self.child_connections = child_connections or []
        self.connected = False
        self.timeout_ms = int(timeout_ms)
        self.program_timeout_ms = int(program_timeout_ms)

        if self.mock:
            self.logger.debug("Starting remote communication using a mock server")
            self.dummy_values = {
                conn: np.random.uniform(0.1, 0.2)
                for conn in self.child_connections
            }
        else:
            self.context = zmq.Context()
            self.host = host
            self.port = port
            self.socket = None

    # ── Socket lifecycle ─────────────────────────────────────────────

    def _create_socket(self, timeout_ms=None):
        """Create a fresh REQ socket.  Closes any existing one first."""
        if not self.mock:
            self._close_socket()
            self.socket = self.context.socket(zmq.REQ)
            t = timeout_ms or self.timeout_ms
            self.socket.setsockopt(zmq.SNDTIMEO, t)
            self.socket.setsockopt(zmq.RCVTIMEO, t)
            self.socket.setsockopt(zmq.LINGER, 0)
            self.socket.connect(f"tcp://{self.host}:{self.port}")

    def _close_socket(self):
        if not self.mock and self.socket is not None:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None

    def _reset_socket(self):
        """Destroy and recreate the socket (recovers from EAGAIN / broken state).

        ZMQ REQ sockets enforce strict send-recv-send-recv ordering.
        After a timeout the socket is stuck waiting for a recv that will
        never come — all subsequent sends fail.  The only recovery is to
        tear down and rebuild the socket.
        """
        self.logger.debug("Resetting REQ socket after failure")
        self._create_socket()

    # ── Connection ───────────────────────────────────────────────────

    def connect_to_remote(self):
        """Send HELLO to verify connectivity.  Returns True/False."""
        if self.mock:
            self.connected = True
            return True

        self._create_socket()
        self.logger.debug(f"Connecting to tcp://{self.host}:{self.port}")

        response = self.send_request({"action": "HELLO", "connection": ""})
        if response is None:
            self.logger.debug("Connection setup failed or timed out.")
            self._close_socket()
            self.connected = False
        else:
            self.logger.debug(f"Connection successful: {response}")
            self.connected = True

        return self.connected

    # ── Core send/receive ────────────────────────────────────────────

    def send_request(self, message, timeout_ms=None):
        """
        Send a JSON request and return the parsed response dict.
        Returns None on timeout or error (instead of raising).
        """
        if self.mock:
            return json.loads(self.mock_request_handler(json.dumps(message)))

        if self.socket is None:
            self.logger.error("send_request called with no socket — call connect_to_remote first")
            return None

        # Temporarily adjust timeout if requested
        effective_timeout = timeout_ms or self.timeout_ms
        self.socket.setsockopt(zmq.SNDTIMEO, effective_timeout)
        self.socket.setsockopt(zmq.RCVTIMEO, effective_timeout)

        try:
            self.socket.send_json(message)
            response = self.socket.recv_json()
            return response

        except zmq.Again:
            # Timeout — the REQ socket is now in a broken send/recv state.
            # We must destroy and recreate it.
            self.logger.error(
                f"ZMQ timeout ({effective_timeout}ms) for action={message.get('action')} "
                f"connection={message.get('connection')}"
            )
            self._reset_socket()
            return None

        except zmq.ZMQError as e:
            self.logger.error(f"ZMQ error during send/receive: {e}")
            self._reset_socket()
            return None

        finally:
            # Restore default timeout
            if self.socket is not None:
                self.socket.setsockopt(zmq.SNDTIMEO, self.timeout_ms)
                self.socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)

    # ── High-level actions ───────────────────────────────────────────

    def program_value(self, connection, value, wait_for_lock=False):
        """
        Send PROGRAM_VALUE to the remote server.

        Args:
            connection: channel/port identifier
            value: setpoint value
            wait_for_lock: if True, tells the server to block until the
                lock converges (used during buffered shots).  Uses the
                extended timeout.  If False (default), the server sets the
                value and returns immediately (manual mode).
        """
        message = {
            "action": "PROGRAM_VALUE",
            "connection": connection,
            "value": value,
            "wait_for_lock": wait_for_lock,
        }
        timeout = self.program_timeout_ms if wait_for_lock else self.timeout_ms
        self.logger.debug(f"program_value: {message} (timeout={timeout}ms)")
        return self.send_request(message, timeout_ms=timeout)

    def check_remote_value(self, connection):
        """Send CHECK_VALUE with default (short) timeout."""
        message = {"action": "CHECK_VALUE", "connection": connection}
        return self.send_request(message)

    # ── Mock ─────────────────────────────────────────────────────────

    def mock_request_handler(self, message_json):
        message = json.loads(message_json)
        action = message.get("action")
        connection = message.get("connection")
        value = message.get("value")

        if action == "HELLO":
            return json.dumps({"status": "SUCCESS"})
        elif action == "PROGRAM_VALUE":
            self.logger.debug(f"Mock: programming {connection} = {value}")
            self.dummy_values[connection] = value
            return json.dumps({"status": "SUCCESS"})
        elif action == "CHECK_VALUE":
            v = self.dummy_values.get(connection, 0.0)
            return json.dumps({"status": "SUCCESS", "value": v})
        else:
            return json.dumps({"status": "ERROR", "message": "Invalid action"})

    # ── Cleanup ──────────────────────────────────────────────────────

    def shutdown(self):
        self._close_socket()
        if not self.mock and hasattr(self, 'context'):
            try:
                self.context.term()
            except Exception:
                pass


class RemoteControlWorker(Worker):
    """
    BLACS worker: bridges the DeviceTab state machine with RemoteCommunication.
    Runs in the BLACS worker subprocess — no Qt here.
    """

    def init(self):
        self.enable_comms = True
        self.h5_filepath = None
        self.child_connections = self.child_output_connections + self.child_monitor_connections

        self.remote_comms = RemoteCommunication(
            host=self.host,
            port=self.port,
            logger=self.logger,
            child_connections=self.child_connections,
            mock=self.mock,
        )

        self._initial_fetch_done = False
        self.initial_monitor_values = {}
        self.final_monitor_values = {}

        # PUB-SUB monitor cache — populated by daemon drain thread.
        # All 4 tab classes (base + 3 subclasses) pass child_monitor_connections
        # via init_kwargs (verified by grep). Empty list is falsy, so devices
        # without monitor children skip the drain thread entirely.
        self._pubsub_cache = {}
        self._pubsub_stop = threading.Event()
        self._monitor_event = None
        self._pubsub_thread = None
        if self.child_monitor_connections:
            try:
                self._monitor_event = Event(
                    f'{self.device_name}_pubsub_monitor',
                    role='wait',
                )
            except TimeoutError as e:
                # Event() raises TimeoutError if it can't connect to the broker
                # within 5 seconds (zprocess.process_tree:334). Should not happen
                # in practice — broker is local and check_broker() ran at module
                # import time. If it does, log and continue without the cache;
                # the worker is still functional, monitor_values just stay empty.
                self.logger.error(
                    f"PUB-SUB drain init failed (broker unreachable): {e}. "
                    f"monitor_values will be empty for this worker session."
                )
                return
            self._pubsub_thread = threading.Thread(
                target=self._pubsub_drain_loop,
                daemon=True,
                name=f'{self.device_name}_pubsub_drain',
            )
            self._pubsub_thread.start()
            self.logger.info(
                f"PUB-SUB drain thread started for "
                f"{len(self.child_monitor_connections)} monitor channels"
            )

    def _pubsub_drain_loop(self):
        """Drain the BLACS-internal EventBroker into self._pubsub_cache.

        Bypasses event.wait()'s identifier filter (which discards messages with
        non-matching identifiers) so all monitor-channel messages on this Event
        are received. Verified empirically (Tests 1, 2): zero loss at 10 kHz
        aggregate, zero cross-leak between devices.
        """
        while not self._pubsub_stop.is_set():
            try:
                with self._monitor_event.sublock:
                    if not self._monitor_event.sub.poll(
                        PUBSUB_DRAIN_POLL_TIMEOUT_MS, zmq.POLLIN
                    ):
                        continue
                    _, event_id, data = self._monitor_event.sub.recv_multipart()
                self._pubsub_cache[event_id.decode('utf8')] = pickle.loads(data)
            except zmq.ContextTerminated:
                # Socket is dead (process shutting down). Exit cleanly.
                return
            except (ValueError, pickle.UnpicklingError) as e:
                # Malformed message — log and keep draining.
                self.logger.warning(
                    f"_pubsub_drain_loop: malformed message: "
                    f"{type(e).__name__}: {e}"
                )
            except Exception as e:
                # Unexpected — log and back off to avoid a tight error loop.
                self.logger.error(
                    f"_pubsub_drain_loop: {type(e).__name__}: {e}",
                    exc_info=True,
                )
                time.sleep(1.0)

    def connect_to_remote(self):
        return self.remote_comms.connect_to_remote()

    def update_settings(self, enable_comms):
        self.enable_comms = enable_comms

    # ── Response handling ────────────────────────────────────────────

    def _check_response(self, response, context=""):
        """Raise on None (timeout) or ERROR status."""
        if response is None:
            raise Exception(f"No response from server (timeout). Context: {context}")
        status = response.get("status", "")
        if status == "SUCCESS":
            return
        msg = response.get("message", "unknown error")
        raise Exception(f"Server error ({context}): {msg}")

    # ── Value checks ─────────────────────────────────────────────────

    def check_remote_values(self):
        """
        Check remote OUTPUT setpoints (called periodically by the tab).
        Returns dict {connection: value} or None.
        """
        if not self.remote_comms.connected:
            return None

        remote_values = {}
        for connection in self.child_output_connections:
            response = self.remote_comms.check_remote_value(connection)
            if response is None:
                self.logger.warning(f"check_remote_values: timeout for {connection}")
                return None
            self._check_response(response, f"check_remote_values({connection})")
            remote_values[connection] = float(response["value"])
        return remote_values

    def check_all_remote_values(self):
        """Check ALL connections (outputs + monitors). Used for shot snapshots."""
        if not self.remote_comms.connected:
            return {}

        remote_values = {}
        for connection in self.child_connections:
            response = self.remote_comms.check_remote_value(connection)
            if response is None:
                self.logger.warning(f"check_all_remote_values: timeout for {connection}")
                continue
            self._check_response(response, f"check_all({connection})")
            remote_values[connection] = float(response["value"])
        return remote_values

    def check_status(self):
        """Check MONITOR connections (legacy name kept for tab compatibility)."""
        if not self.remote_comms.connected:
            return {}

        responses = {}
        for connection in self.child_monitor_connections:
            response = self.remote_comms.check_remote_value(connection)
            if response is None:
                continue
            self._check_response(response, f"check_status({connection})")
            responses[connection] = float(response["value"])
        return responses

    # ── Programming ──────────────────────────────────────────────────

    def mark_initial_fetch_done(self):
        self._initial_fetch_done = True

    def program_manual(self, front_panel_values):
        """Manual mode: set value and return immediately (no lock wait)."""
        if not self.remote_comms.connected:
            return {}
        if not self._initial_fetch_done:
            return {}  # Don't overwrite server values before first fetch

        for connection in self.child_output_connections:
            value = front_panel_values[connection]
            response = self.remote_comms.program_value(
                connection, value, wait_for_lock=False
            )
            self._check_response(response, f"program_manual({connection}={value})")
        return {}

    # ── Shot lifecycle ───────────────────────────────────────────────

    def transition_to_buffered(self, device_name, h5_filepath, front_panel_values, fresh):
        """Buffered mode: set value and wait for lock convergence."""
        if not self.enable_comms:
            return {}

        _t0 = time.perf_counter()
        try:
            with h5py.File(h5_filepath, 'r') as f:
                group = f['devices'][self.device_name]
                if 'remote_device_operation' not in group:
                    return {}
                table = group['remote_device_operation'][:]

            # All h5 access done — program outside the zlock so that exceptions
            # (e.g. lock-wait timeout) don't trigger "lock not held" on cleanup.
            if not self.remote_comms.connected:
                raise Exception(
                    "Cannot program remote device: connection not established.\n"
                    "Please check connection and try again."
                )

            self.h5_filepath = h5_filepath

            for connection in table.dtype.names:
                value = float(table[0][connection])
                self.logger.debug(f"transition_to_buffered: programming {connection} = {value}")
                wait = getattr(self, 'wait_for_lock', False)
                response = self.remote_comms.program_value(
                    connection, value, wait_for_lock=wait
                )
                self._check_response(response, f"buffered_program({connection}={value})")

            # Snapshot monitor values from PUB-SUB cache (no REQ-REP round-trip).
            # The cache is updated at ~4 Hz by the tab's subscriber thread; for the
            # slow physical quantities these devices monitor (motor positions,
            # laser temperatures, lock setpoints), this is far fresher than needed.
            # Mirrors the pattern proven in RasteringDevice/blacs_workers.py:85.
            # dict() copy is atomic under the GIL; thread-safe vs the drain
            # thread's per-key writes. No lock needed.
            self.initial_monitor_values = dict(self._pubsub_cache)
            self.logger.info(
                f"initial_monitor_values: "
                f"{len(self.initial_monitor_values)} channels"
            )

            return {}
        finally:
            _dt_ms = (time.perf_counter() - _t0) * 1000
            self.logger.info(f"PERF transition_to_buffered: {_dt_ms:.1f} ms")

    def post_experiment(self):
        _t0 = time.perf_counter()
        try:
            if self.initial_monitor_values:
                # Final values from PUB-SUB cache (no REQ-REP round-trip).
                # dict() copy is atomic under the GIL; thread-safe vs the drain thread.
                self.final_monitor_values = dict(self._pubsub_cache)

                with h5py.File(self.h5_filepath, 'a') as hdf5_file:
                    self._save_monitor_values_to_hdf5(
                        hdf5_file, 'initial_monitor_values', self.initial_monitor_values
                    )
                    self._save_monitor_values_to_hdf5(
                        hdf5_file, 'final_monitor_values', self.final_monitor_values
                    )

            self.initial_monitor_values = {}
            self.final_monitor_values = {}
            return True
        finally:
            _dt_ms = (time.perf_counter() - _t0) * 1000
            self.logger.info(f"PERF post_experiment: {_dt_ms:.1f} ms")

    def _save_monitor_values_to_hdf5(self, hdf5_file, group_name, monitor_values):
        if not monitor_values:
            return

        dtypes = [(name, np.float64) for name in monitor_values.keys()]
        static_value_table = np.zeros(1, dtype=dtypes)
        for connection, value in monitor_values.items():
            static_value_table[connection] = value

        try:
            group = hdf5_file[f'/data/{self.device_name}/monitor_values']
        except KeyError:
            group = hdf5_file.create_group(f'/data/{self.device_name}/monitor_values')

        group.create_dataset(group_name, data=static_value_table)

    def transition_to_manual(self):
        return True

    def abort_transition_to_buffered(self):
        self.initial_monitor_values = {}
        self.final_monitor_values = {}
        return True

    def abort_buffered(self):
        self.initial_monitor_values = {}
        self.final_monitor_values = {}
        return True

    def shutdown(self):
        self.remote_comms.shutdown()
