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

# v2 protocol foundation. PR 1 ships in master at commit ef24a6d
# (refined cf394d3 — REQ transport TimeoutError translation).
from external_gui_lib.zmq_v2 import (
    InMemoryTransport,
    PROTOCOL_VERSION,
    RemoteControlServerBase,
    RequestIdCounter,
    ZmqReqTransport,
    encode_reply,
    encode_request,
    handler,
    parse_envelope,
)

# PUB-SUB monitor cache constants (see design spec Tasks 1, 2, 3, 6).
PUBSUB_DRAIN_POLL_TIMEOUT_MS = 500   # max idle shutdown latency
PUBSUB_SHUTDOWN_JOIN_TIMEOUT = 1.0   # seconds; daemon=True is the safety net


# Default timeouts (ms)
DEFAULT_TIMEOUT_MS = 5000        # General REQ-REP operations (HELLO, CHECK_VALUE, manual programs)
PROGRAM_TIMEOUT_MS = 120_000     # PROGRAM_VALUE with wait_for_lock — server may block up to 60s


# Errors classed as "operational, not a crash". Worker code that catches
# Exception around send_request results today expects raised Exceptions
# on all non-SUCCESS replies; this base lives below the surface.
class RemoteRequestError(Exception):
    """Server replied with non-SUCCESS status. Carries the v2 error dict.

    Status codes per spec section 1.3: ERROR, REJECTED, TIMEOUT,
    UNKNOWN_CONNECTION.
    """

    def __init__(self, status, error_dict, context=""):
        self.status = status
        self.error_dict = error_dict or {}
        self.code = self.error_dict.get("code", "unknown_code")
        self.message = self.error_dict.get("message", "")
        self.retryable = bool(self.error_dict.get("retryable", False))
        super().__init__(
            f"{context}: server {status} [{self.code}] {self.message}"
        )


class RemoteRetryableError(RemoteRequestError):
    """v2 server reported a transient error (error.retryable == True).

    Distinct subclass so a future retry layer can catch retryable failures
    specifically (e.g. ``except RemoteRetryableError: retry_once_then_raise``)
    without changing the v1 catch-all behavior. Today's BLACS callers
    catch generic Exception around _check_response and treat all non-
    SUCCESS as fatal — retry behavior is a deferred follow-up.
    """


class RemoteMalformedReplyError(RemoteRequestError):
    """v2 reply could not be parsed as a valid envelope.

    Distinguishes a server bug (garbled JSON, missing required keys)
    from a transport timeout (which returns None). Surfaces the actual
    parse error so debuggers don't waste time chasing a phantom timeout.
    """

    def __init__(self, parse_error, raw_bytes, context=""):
        super().__init__(
            status="ERROR",
            error_dict={
                "code": "malformed_reply",
                "message": "could not parse v2 envelope: %s" % parse_error,
                "retryable": False,
            },
            context=context,
        )
        self.parse_error = parse_error
        self.raw_bytes = raw_bytes


class _MockRemoteServer(RemoteControlServerBase):
    """In-memory v2 mock server backing RemoteCommunication(mock=True).

    Per Q4 hard sunset, BLACS-side ships v2-only — the v1
    mock_request_handler is replaced by this v2 mini-server. The mock
    is driven inline inside send_request via InMemoryTransport.pair():
    no thread, no socket, deterministic single-step dispatch.
    """

    CAPABILITIES = frozenset()

    def __init__(self, transport, child_connections, logger):
        super().__init__("MockRemoteServer", transport)
        self._dummy_values = {
            conn: float(np.random.uniform(0.1, 0.2))
            for conn in child_connections
        }
        self._logger = logger

    @handler("PROGRAM_VALUE")
    def _handle_program(self, connection, value, args, request_id):
        self._dummy_values[connection] = value
        if self._logger is not None:
            self._logger.debug(f"Mock: programming {connection} = {value}")
        return encode_reply(status="SUCCESS", request_id=request_id)

    @handler("CHECK_VALUE")
    def _handle_check(self, connection, value, args, request_id):
        v = self._dummy_values.get(connection, 0.0)
        return encode_reply(status="SUCCESS", request_id=request_id, value=v)


class RemoteCommunication:
    """
    ZMQ REQ-REP v2 protocol client for a remote device server.

    v2 envelope (spec section 1):
      Request:  {"v": 2, "id": uint64, "action": str, "connection": str,
                 "value": any, "args": {...}, "request_timestamp": float}
      Reply:    {"v": 2, "id": uint64, "status": "SUCCESS"|"ERROR"|"REJECTED"|
                 "TIMEOUT"|"UNKNOWN_CONNECTION", "value": any,
                 "error": {"code": str, "message": str, "retryable": bool},
                 "server_timestamp": float}

    Actions: "HELLO", "PROGRAM_VALUE", "CHECK_VALUE", "PING".

    Q4 §10-resolved: this client ships v2-only. Servers refuse v1
    envelopes; the cutover is atomic across all 3 GUI servers + this
    client in one coordinated round.
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

        # Q2 §10-resolved: every BLACS-side request MUST carry an id.
        self._id_counter = RequestIdCounter()

        self._transport = None
        self._mock_server = None

        if self.mock:
            self.logger.debug("Starting remote communication using a mock server")
            client_t, server_t = InMemoryTransport.pair()
            self._transport = client_t
            self._mock_server = _MockRemoteServer(
                server_t, self.child_connections, self.logger)
        else:
            self.host = host
            self.port = port

    # ── Transport lifecycle ──────────────────────────────────────────

    def _create_transport(self, timeout_ms=None):
        """Create a fresh REQ transport. Closes any existing one first."""
        if self.mock:
            return  # InMemoryTransport pair is set up once in __init__.
        self._close_transport()
        t = timeout_ms or self.timeout_ms
        self._transport = ZmqReqTransport(
            f"tcp://{self.host}:{self.port}",
            recv_timeout_ms=t,
            send_timeout_ms=t,
        )

    def _close_transport(self):
        if self.mock:
            return  # paired InMemoryTransport closes with the object.
        if self._transport is not None:
            try:
                self._transport.close()
            except Exception:
                pass
            self._transport = None

    def _reset_transport(self):
        """Destroy and recreate the transport (recovers from broken state).

        ZMQ REQ sockets enforce strict send-recv-send-recv ordering.
        After a timeout the socket is stuck waiting for a recv that will
        never come — all subsequent sends fail. The only recovery is to
        tear down and rebuild the transport.
        """
        if self.mock:
            return
        self.logger.debug("Resetting REQ transport after failure")
        self._create_transport()

    # ── Connection ───────────────────────────────────────────────────

    def connect_to_remote(self):
        """Send HELLO to verify connectivity. Returns True/False."""
        if self.mock:
            # Drive the mock server once to ack the HELLO; mock servers
            # don't need a transport bind.
            self.connected = True
            return True

        self._create_transport()
        self.logger.debug(f"Connecting to tcp://{self.host}:{self.port}")

        try:
            response = self._raw_request("HELLO", connection="", args=None)
        except RemoteRequestError as exc:
            self.logger.debug(f"HELLO refused by server: {exc}")
            self._close_transport()
            self.connected = False
            return False

        if response is None:
            self.logger.debug("Connection setup failed or timed out.")
            self._close_transport()
            self.connected = False
        else:
            self.logger.debug(f"Connection successful: server={response.get('server')!r} "
                              f"capabilities={response.get('capabilities')!r}")
            self.connected = True

        return self.connected

    # ── Core send/receive ────────────────────────────────────────────

    def _raw_request(self, action, *, connection="", value=None, args=None,
                     timeout_ms=None):
        """Build v2 envelope, send via transport, parse reply.

        Returns:
          * parsed reply dict on SUCCESS.
          * None on transport timeout or transport error.

        Raises:
          * RemoteRequestError on non-SUCCESS server reply (ERROR /
            REJECTED / TIMEOUT / UNKNOWN_CONNECTION). Callers that
            previously checked status manually can catch this and map
            back to None / exception.
        """
        if self._transport is None:
            self.logger.error(
                "_raw_request called with no transport — call connect_to_remote first")
            return None

        envelope = encode_request(
            action=action,
            request_id=self._id_counter.next_id(),
            connection=connection,
            value=value,
            args=args,
        )
        effective_timeout = timeout_ms or self.timeout_ms

        try:
            self._transport.send(envelope)
            # Mock: drive the in-memory server inline. Paired-queue
            # send_q feeds the server's recv; serve_once dispatches and
            # writes the reply back; our recv below picks it up.
            if self.mock:
                self._mock_server.serve_once(timeout_ms=100)
            raw_reply = self._transport.recv(timeout_ms=effective_timeout)
        except TimeoutError:
            self.logger.error(
                f"ZMQ timeout ({effective_timeout}ms) for action={action} "
                f"connection={connection}")
            self._reset_transport()
            return None
        except zmq.ZMQError as e:
            self.logger.error(f"ZMQ error during send/receive: {e}")
            self._reset_transport()
            return None
        except Exception as e:  # transport closed mid-call etc.
            self.logger.error(f"Transport error during send/receive: {e}")
            self._reset_transport()
            return None

        try:
            reply = parse_envelope(raw_reply)
        except ValueError as e:
            self.logger.error(
                f"Malformed v2 reply for action={action} connection={connection}: {e}")
            # Raise (not return None) so the caller's _check_response
            # surfaces "malformed_reply" instead of "timeout" -- a real
            # server bug should not be diagnosed as a network problem.
            raise RemoteMalformedReplyError(
                parse_error=str(e), raw_bytes=raw_reply,
                context=f"action={action} connection={connection}",
            )

        # Version enforcement was one-directional: the server refuses v1
        # requests, but nothing checked the reply. A v1 GUI answering a v2
        # client surfaced as a misleading 5s timeout on every setpoint.
        if reply.get("v") != PROTOCOL_VERSION:
            raise RemoteRequestError(
                status="ERROR",
                error_dict={
                    "code": "protocol_version_mismatch",
                    "message": (
                        f"remote GUI replied with protocol v{reply.get('v')!r}, "
                        f"expected v{PROTOCOL_VERSION} — that GUI is still on v1; "
                        "complete the zmq v2 cutover on it "
                        "(docs/zmq-v2-cutover-runbook.md)"
                    ),
                    "retryable": False,
                },
                context=f"action={action} connection={connection}",
            )

        status = reply.get("status", "")
        if status == "SUCCESS":
            return reply
        err = reply.get("error") or {}
        # Distinguish retryable failures so a future retry layer can
        # catch RemoteRetryableError specifically. Today's BLACS callers
        # catch the parent Exception class -- same behavior either way.
        exc_cls = (RemoteRetryableError if err.get("retryable") is True
                   else RemoteRequestError)
        raise exc_cls(
            status=status,
            error_dict=err,
            context=f"action={action} connection={connection}",
        )

    # ── High-level actions ───────────────────────────────────────────

    def program_value(self, connection, value, wait_for_lock=False):
        """Send PROGRAM_VALUE to the remote server.

        Args:
            connection: channel/port identifier
            value: setpoint value
            wait_for_lock: if True, tells the server to block until the
                lock converges (used during buffered shots). Uses the
                extended timeout. If False (default), the server sets the
                value and returns immediately (manual mode).

        Returns parsed v2 reply dict on SUCCESS, or None on transport
        timeout. Raises RemoteRequestError on non-SUCCESS server reply.

        Q2 §10-resolved: wait_for_lock moves into the v2 `args` dict.
        """
        timeout = self.program_timeout_ms if wait_for_lock else self.timeout_ms
        # Always send the key explicitly -- absence must never be
        # interpretable by servers (HF defaulted absent->True pre-2026-07-07).
        # A single-key dict is truthy even when the value is False, so
        # encode_request's `if args:` guard keeps it in the envelope.
        args = {"wait_for_lock": bool(wait_for_lock)}
        self.logger.debug(
            f"program_value: connection={connection} value={value} "
            f"wait_for_lock={wait_for_lock} timeout={timeout}ms")
        try:
            return self._raw_request(
                "PROGRAM_VALUE",
                connection=connection, value=value, args=args,
                timeout_ms=timeout,
            )
        except RemoteRequestError as exc:
            # Preserve historical interface: callers expect dict-or-None
            # and inspect status themselves. Translate the raise back
            # into a v1-shaped dict so callers don't need refactoring.
            return {
                "status": exc.status,
                "value": None,
                "error": exc.error_dict,
                # v1 callers used `message`; keep a back-compat alias.
                "message": exc.message,
            }

    def check_remote_value(self, connection):
        """Send CHECK_VALUE with default (short) timeout."""
        try:
            return self._raw_request(
                "CHECK_VALUE", connection=connection, value=None, args=None,
            )
        except RemoteRequestError as exc:
            return {
                "status": exc.status,
                "value": None,
                "error": exc.error_dict,
                "message": exc.message,
            }

    # ── Cleanup ──────────────────────────────────────────────────────

    def shutdown(self):
        self._close_transport()


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
        """Raise on None (timeout) or any non-SUCCESS status.

        v2 statuses (spec §1.3): SUCCESS, ERROR, REJECTED, TIMEOUT,
        UNKNOWN_CONNECTION. v2 errors live in
        response['error']['{code,message,retryable}']. Falls back to v1
        response['message'] for back-compat with the RemoteCommunication
        translation layer.

        Retry policy (NOT YET IMPLEMENTED): error.retryable is surfaced
        in the raised exception's message + propagates via the upstream
        RemoteRetryableError class. A future retry layer in program_manual
        / buffered_program can catch RemoteRetryableError specifically and
        retry once before bubbling to runmanager. Today's callers catch
        Exception generically -- same behavior as v1.
        """
        if response is None:
            raise Exception(f"No response from server (timeout). Context: {context}")
        status = response.get("status", "")
        if status == "SUCCESS":
            return
        err = response.get("error") or {}
        code = err.get("code", "")
        msg = err.get("message") or response.get("message") or "unknown error"
        prefix = f"[{code}] " if code else ""
        retry_hint = " (retryable)" if err.get("retryable") is True else ""
        raise Exception(
            f"Server {status} ({context}): {prefix}{msg}{retry_hint}")

    def _skip_non_success_read(self, connection, response, context):
        """Read-path policy: a non-SUCCESS reply to a value CHECK means the
        channel isn't readable yet (e.g. UNKNOWN_CONNECTION for an
        un-programmed setpoint). Log and skip -- NEVER raise on a read (a
        raising periodic poll bricks the tab with a persistent error banner).
        Write paths keep using _check_response (raise). Single source of the
        read policy for all subclasses. See
        memory/feedback_remotecontrol-base-is-the-contract.
        """
        if response.get("status") == "SUCCESS":
            return False
        msg = (response.get("error") or {}).get("message") or response.get("message", "")
        self.logger.warning(
            f"{context}: skipping {connection} ({response.get('status')}: {msg})")
        return True

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
            if self._skip_non_success_read(connection, response, "check_remote_values"):
                continue
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
            if self._skip_non_success_read(connection, response, "check_all_remote_values"):
                continue
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
            if self.initial_monitor_values and self.h5_filepath:
                # Final values from PUB-SUB cache (no REQ-REP round-trip).
                # dict() copy is atomic under the GIL; thread-safe vs the drain thread.
                self.final_monitor_values = dict(self._pubsub_cache)
                self.logger.info(
                    f"final_monitor_values: "
                    f"{len(self.final_monitor_values)} channels"
                )

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
        # Stop drain thread first so no further cache writes happen during
        # teardown. daemon=True guarantees process exit even if join times out.
        self._pubsub_stop.set()
        if self._pubsub_thread is not None:
            self._pubsub_thread.join(timeout=PUBSUB_SHUTDOWN_JOIN_TIMEOUT)
        self.remote_comms.shutdown()
