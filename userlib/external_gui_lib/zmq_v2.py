"""ZMQ v2 RemoteControl protocol foundation.

Implements the protocol described in ``docs/remotecontrol-zmq-protocol-v2.md``:

  * Section 1: JSON envelope (HELLO version negotiation, request, reply with
    structured error).
  * Section 2: Decorator-based dispatch (``@handler("PROGRAM_VALUE")``).
  * Section 3: Optional ``PING`` action for liveness probes.
  * Section 5: Transport ABC + concrete implementations
    (``ZmqReqTransport``, ``ZmqRepTransport``, ``InMemoryTransport`` for
    tests).
  * Section 6: Structured logging via ``logging.getLogger(
    "remotecontrol.{server_name}.req")``.

Per the §10-resolved sign-off:

  * Q1 -- ``connections`` glob in HELLO reply is OPTIONAL; hubs SHOULD
    advertise, single-instance servers MAY omit. Matching is prefix-only
    (no fnmatch/regex). See ``client_matches_advertised`` helper.
  * Q2 -- ``id`` is REQUIRED on requests from BLACS-side
    ``RemoteCommunication`` (per-instance monotonic counter); OPTIONAL
    from other clients. Server MUST echo if present.
  * Q3 -- ``capabilities`` is an array of strings from
    ``CANONICAL_CAPABILITIES``. The frozenset is the anti-drift pin.
  * Q4 -- HARD SUNSET. v2 servers REFUSE v1 requests with
    ``v1_protocol_refused`` error. There is no dual-path code.

PR 1 of 4 (this file): protocol foundation, no behavior change.
PR 2-4 will port BigSky, HF_Locking, Rastering servers onto
``RemoteControlServerBase`` and update ``RemoteCommunication.py`` to
emit v2 envelopes.
"""
from __future__ import annotations

import itertools
import json
import logging
import queue
import time
from abc import abstractmethod
from typing import Any, Callable, Optional, Protocol


# Q3 anti-drift pin. New capability strings require a 2-step PR:
# (1) extend this frozenset, (2) use the new capability. Tests in
# `userlib/external_gui_lib/tests/` pin this literal.
CANONICAL_CAPABILITIES = frozenset({"monitors", "heartbeat", "wait_for_lock"})

PROTOCOL_VERSION = 2


# --------------------------------------------------------------------------
# Transport ABC (§5)
# --------------------------------------------------------------------------


class Transport(Protocol):
  """Abstract bidirectional framed message channel.

  Concrete implementations live below: ``ZmqReqTransport`` /
  ``ZmqRepTransport`` (production), ``InMemoryTransport`` (tests).
  """

  def send(self, frame: bytes) -> None: ...

  def recv(self, timeout_ms: int = -1) -> bytes: ...

  def close(self) -> None: ...


class InMemoryTransport:
  """Paired in-memory queue transport for tests.

  Use ``InMemoryTransport.pair()`` to create a (client, server) pair
  that share two queues (one each direction). Drop-in for
  ``ZmqReqTransport``/``ZmqRepTransport`` -- no sockets bound, no
  blocking on system resources.

  Example::

      client_t, server_t = InMemoryTransport.pair()
      client_t.send(b'{"v": 2, "action": "HELLO"}')
      raw = server_t.recv(timeout_ms=100)
      server_t.send(b'{"v": 2, "status": "SUCCESS"}')
      reply = client_t.recv(timeout_ms=100)
  """

  def __init__(self, send_q: "queue.Queue[bytes]",
               recv_q: "queue.Queue[bytes]") -> None:
    self._send_q = send_q
    self._recv_q = recv_q
    self._closed = False

  @classmethod
  def pair(cls) -> "tuple[InMemoryTransport, InMemoryTransport]":
    """Return (side_a, side_b) sharing two queues; whatever a sends, b receives."""
    a_to_b: "queue.Queue[bytes]" = queue.Queue()
    b_to_a: "queue.Queue[bytes]" = queue.Queue()
    return cls(a_to_b, b_to_a), cls(b_to_a, a_to_b)

  def send(self, frame: bytes) -> None:
    if self._closed:
      raise RuntimeError("transport closed")
    self._send_q.put(frame)

  def recv(self, timeout_ms: int = -1) -> bytes:
    if self._closed:
      raise RuntimeError("transport closed")
    block = timeout_ms != 0
    timeout_s: Optional[float] = None if timeout_ms < 0 else timeout_ms / 1000.0
    try:
      return self._recv_q.get(block=block, timeout=timeout_s)
    except queue.Empty as exc:
      raise TimeoutError(
          "InMemoryTransport.recv timed out after %d ms" % timeout_ms
      ) from exc

  def close(self) -> None:
    self._closed = True


class ZmqReqTransport:
  """Production REQ-side transport (BLACS-side client). Lazy zmq import so
  that test-only users of this module don't have to install pyzmq."""

  def __init__(self, address: str, recv_timeout_ms: int = 5000,
               send_timeout_ms: int = 5000) -> None:
    import zmq
    self._zmq = zmq
    self._ctx = zmq.Context.instance()
    self._sock = self._ctx.socket(zmq.REQ)
    self._sock.setsockopt(zmq.LINGER, 0)
    self._sock.setsockopt(zmq.RCVTIMEO, recv_timeout_ms)
    self._sock.setsockopt(zmq.SNDTIMEO, send_timeout_ms)
    self._sock.connect(address)
    self._address = address

  def send(self, frame: bytes) -> None:
    self._sock.send(frame)

  def recv(self, timeout_ms: int = -1) -> bytes:
    if timeout_ms >= 0:
      self._sock.setsockopt(self._zmq.RCVTIMEO, timeout_ms)
    return self._sock.recv()

  def close(self) -> None:
    self._sock.close(linger=0)


class ZmqRepTransport:
  """Production REP-side transport (GUI server)."""

  def __init__(self, address: str, recv_timeout_ms: int = -1) -> None:
    import zmq
    self._zmq = zmq
    self._ctx = zmq.Context.instance()
    self._sock = self._ctx.socket(zmq.REP)
    self._sock.setsockopt(zmq.LINGER, 0)
    if recv_timeout_ms >= 0:
      self._sock.setsockopt(zmq.RCVTIMEO, recv_timeout_ms)
    self._sock.bind(address)
    self._address = address

  def send(self, frame: bytes) -> None:
    self._sock.send(frame)

  def recv(self, timeout_ms: int = -1) -> bytes:
    if timeout_ms >= 0:
      self._sock.setsockopt(self._zmq.RCVTIMEO, timeout_ms)
    return self._sock.recv()

  def close(self) -> None:
    self._sock.close(linger=0)


# --------------------------------------------------------------------------
# Envelope helpers (§1)
# --------------------------------------------------------------------------


def encode_request(action: str, *, request_id: Optional[int] = None,
                   connection: str = "", value: Any = None,
                   args: Optional[dict] = None) -> bytes:
  """Build a v2 request envelope. ``request_id`` MUST be set by
  ``RemoteCommunication`` (per Q2). Returns JSON-encoded bytes."""
  envelope: dict[str, Any] = {"v": PROTOCOL_VERSION, "action": action}
  if request_id is not None:
    envelope["id"] = request_id
  if connection:
    envelope["connection"] = connection
  if value is not None:
    envelope["value"] = value
  if args:
    envelope["args"] = args
  envelope["request_timestamp"] = time.time()
  return json.dumps(envelope).encode("utf-8")


def encode_reply(*, status: str, request_id: Optional[int] = None,
                 value: Any = None, error: Optional[dict] = None,
                 extra: Optional[dict] = None) -> bytes:
  """Build a v2 reply envelope.

  ``status`` must be one of: "SUCCESS", "ERROR", "REJECTED", "TIMEOUT",
  "UNKNOWN_CONNECTION". ``error`` MUST be present iff ``status != "SUCCESS"``.
  ``extra`` lets HELLO replies attach ``server`` / ``capabilities`` / etc.
  """
  envelope: dict[str, Any] = {"v": PROTOCOL_VERSION, "status": status}
  if request_id is not None:
    envelope["id"] = request_id
  if value is not None:
    envelope["value"] = value
  if error is not None:
    envelope["error"] = error
  envelope["server_timestamp"] = time.time()
  if extra:
    envelope.update(extra)
  return json.dumps(envelope).encode("utf-8")


def v1_refused_reply(request_id: Optional[int] = None) -> bytes:
  """Q4 hard-sunset response: v2 servers REFUSE v1 requests."""
  return encode_reply(
      status="ERROR",
      request_id=request_id,
      error={
          "code": "v1_protocol_refused",
          "message": ("Server requires v2 protocol; client must include "
                      "'v': 2 in requests"),
          "retryable": False,
      },
  )


def parse_envelope(raw: bytes) -> dict:
  """Decode a v2 envelope. Raises ``ValueError`` on parse failure."""
  try:
    decoded = json.loads(raw.decode("utf-8"))
  except (UnicodeDecodeError, json.JSONDecodeError) as exc:
    raise ValueError("not valid v2 envelope: %s" % exc) from exc
  if not isinstance(decoded, dict):
    raise ValueError("v2 envelope must decode to a dict; got %r"
                     % type(decoded).__name__)
  return decoded


def client_matches_advertised(connection: str,
                              advertised: Optional[list]) -> bool:
  """Q1 prefix-match check. Returns True if ``connection`` matches any
  advertised pattern, OR if ``advertised`` is None/empty (no advertisement
  means no fail-fast check; server is the authority)."""
  if not advertised:
    return True
  for pattern in advertised:
    if not isinstance(pattern, str):
      continue
    prefix = pattern.rstrip("*")
    if connection.startswith(prefix):
      return True
  return False


# --------------------------------------------------------------------------
# Dispatch decorator (§2)
# --------------------------------------------------------------------------


_HANDLER_ATTR = "_remotecontrol_v2_action"


def handler(action: str) -> Callable:
  """Mark a ``RemoteControlServerBase`` method as the dispatcher for
  ``action``. The base class introspects the subclass at registration
  time and builds an action -> bound-method map.

  Example::

      class MyServer(RemoteControlServerBase):
          @handler("PROGRAM_VALUE")
          def _handle_program(self, conn, value, args, request_id):
              ...
  """
  if not isinstance(action, str) or not action:
    raise ValueError("@handler requires a non-empty action string")

  def deco(fn: Callable) -> Callable:
    setattr(fn, _HANDLER_ATTR, action)
    return fn

  return deco


# --------------------------------------------------------------------------
# RemoteControlServerBase
# --------------------------------------------------------------------------


class RemoteControlServerBase:
  """Base class for v2 RemoteControl server implementations.

  Subclasses register handlers via ``@handler("ACTION")``. The base
  class owns the receive loop scaffolding, JSON parse, envelope
  construction, version check, HELLO/PING reserved-action handlers,
  and error wrapping.

  Threading model is LEFT TO THE SUBCLASS. Different GUIs already have
  different threading patterns (HF: QThread, Rastering: daemon thread,
  BigSky: class + futures). This base class is intentionally threading-
  agnostic; it provides building blocks (``serve_once``,
  ``_build_hello_reply``) that the subclass invokes from its own
  scheduler.
  """

  #: Subclasses override to advertise. Set ``None`` (or omit) to skip
  #: the optional ``connections`` advertisement in HELLO.
  ADVERTISED_CONNECTIONS: Optional[list[str]] = None

  #: Subclasses override. MUST be a subset of CANONICAL_CAPABILITIES.
  CAPABILITIES: frozenset[str] = frozenset()

  def __init__(self, server_name: str, transport: Transport) -> None:
    self._server_name = server_name
    self._transport = transport
    self._log = logging.getLogger("remotecontrol.%s.req" % server_name)
    self._started_at = time.time()
    if not self.CAPABILITIES.issubset(CANONICAL_CAPABILITIES):
      bad = self.CAPABILITIES - CANONICAL_CAPABILITIES
      raise ValueError(
          "%s declares non-canonical capabilities %r (allowed: %r). "
          "To add a new capability, extend CANONICAL_CAPABILITIES first."
          % (server_name, sorted(bad), sorted(CANONICAL_CAPABILITIES))
      )
    self._handlers: dict[str, Callable] = self._build_handler_map()

  def _build_handler_map(self) -> dict[str, Callable]:
    """Walk the MRO and collect @handler-decorated methods."""
    table: dict[str, Callable] = {}
    for klass in type(self).__mro__:
      for name, member in klass.__dict__.items():
        action = getattr(member, _HANDLER_ATTR, None)
        if action is None:
          continue
        if action not in table:
          table[action] = getattr(self, name)
    return table

  # ---- Reserved-action handlers (§2.2) ----

  def _handle_hello(self, request_id: Optional[int]) -> bytes:
    extra: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "server": self._server_name,
        "capabilities": sorted(self.CAPABILITIES),
    }
    if self.ADVERTISED_CONNECTIONS:
      extra["connections"] = list(self.ADVERTISED_CONNECTIONS)
    return encode_reply(status="SUCCESS", request_id=request_id, extra=extra)

  def _handle_ping(self, request_id: Optional[int]) -> bytes:
    extra = {
        "uptime_seconds": time.time() - self._started_at,
        "server": self._server_name,
    }
    return encode_reply(status="SUCCESS", request_id=request_id, extra=extra)

  # ---- Main loop entry point ----

  def serve_once(self, *, timeout_ms: int = -1) -> bool:
    """Receive a single frame, dispatch, send the reply.

    Returns ``True`` on successful round-trip, ``False`` on timeout.
    Subclasses call this from their own threading scaffold (QThread.run,
    daemon-thread loop body, futures executor, etc.).
    """
    try:
      raw = self._transport.recv(timeout_ms=timeout_ms)
    except TimeoutError:
      return False
    self._dispatch_raw(raw)
    return True

  def _dispatch_raw(self, raw: bytes) -> None:
    """Parse raw bytes, dispatch, send reply. Internal entry point."""
    request_id: Optional[int] = None
    t0 = time.perf_counter()
    try:
      envelope = parse_envelope(raw)
    except ValueError as exc:
      reply = encode_reply(
          status="ERROR",
          error={
              "code": "envelope_parse_error",
              "message": str(exc),
              "retryable": False,
          },
      )
      self._log_request(action="<parse-error>", request_id=None,
                        status="ERROR", latency_s=time.perf_counter() - t0,
                        error_code="envelope_parse_error")
      self._transport.send(reply)
      return

    request_id = envelope.get("id")

    # Q4 hard sunset: v1 requests are refused.
    if envelope.get("v") != PROTOCOL_VERSION:
      reply = v1_refused_reply(request_id=request_id)
      self._log_request(action=envelope.get("action", "<v1>"),
                        request_id=request_id, status="ERROR",
                        latency_s=time.perf_counter() - t0,
                        error_code="v1_protocol_refused")
      self._transport.send(reply)
      return

    action = envelope.get("action")
    status: str = "SUCCESS"
    err_code: Optional[str] = None
    if action == "HELLO":
      reply = self._handle_hello(request_id)
    elif action == "PING":
      reply = self._handle_ping(request_id)
    elif action in self._handlers:
      try:
        result = self._handlers[action](
            envelope.get("connection", ""),
            envelope.get("value"),
            envelope.get("args") or {},
            request_id,
        )
        if not isinstance(result, (bytes, bytearray)):
          # Handlers MUST return bytes (via `encode_reply`). Returning a
          # raw dict is ambiguous — the early v2 draft tried to wrap it
          # but silently discarded status/error keys, which is a footgun.
          # See review finding 2026-05-22 (parent code-review).
          raise TypeError(
              "@handler %r returned %s; must return bytes via encode_reply()"
              % (action, type(result).__name__))
        reply = result
        # Trust handler-encoded reply: parse minimally for log fields.
        # This single parse replaces the prior post-hoc JSON re-decode of
        # every reply on the hot path.
        try:
          decoded = json.loads(reply.decode("utf-8"))
          status = decoded.get("status", "?")
          err_code = (decoded.get("error") or {}).get("code")
        except Exception:
          status = "?"
      except Exception as exc:
        err_code = "handler_exception"
        status = "ERROR"
        reply = encode_reply(
            status="ERROR",
            request_id=request_id,
            error={
                "code": err_code,
                "message": "%s: %s" % (type(exc).__name__, exc),
                "retryable": False,
            },
        )
    else:
      status = "ERROR"
      err_code = "unknown_action"
      reply = encode_reply(
          status=status,
          request_id=request_id,
          error={
              "code": err_code,
              "message": "unknown action: %r" % action,
              "retryable": False,
          },
      )

    self._log_request(action=action or "<missing>", request_id=request_id,
                      status=status, latency_s=time.perf_counter() - t0,
                      error_code=err_code)
    self._transport.send(reply)

  # ---- Observability (§6) ----

  def _log_request(self, *, action: str, request_id: Optional[int],
                   status: str, latency_s: float,
                   error_code: Optional[str]) -> None:
    self._log.info(
        "action=%s id=%s status=%s latency_ms=%.2f error_code=%s",
        action, request_id, status, latency_s * 1000.0, error_code or "",
    )


# --------------------------------------------------------------------------
# BLACS-side request id counter helper
# --------------------------------------------------------------------------


class RequestIdCounter:
  """Per-(client, server) monotonic request id source.

  Used by ``RemoteCommunication`` to satisfy Q2 (id REQUIRED on
  BLACS-side requests). Resets on reconnect -- the broken connection
  itself is the correlation breakpoint.
  """

  def __init__(self) -> None:
    self._counter = itertools.count()

  def next_id(self) -> int:
    return next(self._counter)

  def reset(self) -> None:
    self._counter = itertools.count()
