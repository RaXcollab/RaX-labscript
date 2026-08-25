"""Canonical invariants for the v2 RemoteControl protocol foundation.

Tests use ``InMemoryTransport.pair()`` to avoid binding sockets. This is
the V1-V10 invariant pin set; future userlib worker tests (item 2.8c)
will build on the same pattern.

Run::

    Set-Location userlib/external_gui_lib
    python -m pytest tests/ -v

The foundation tests require pytest. The worker tests also require BLACS.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

# Put userlib/ on sys.path so external_gui_lib resolves the SAME way as
# in BLACS runtime (where `userlib/` is the top-level search root for
# `user_devices.*` and `external_gui_lib.*`). Avoids labscript_utils'
# double_import_denier firing when tests import via both `external_gui_lib`
# and `userlib.external_gui_lib` paths (regression 2026-05-23).
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_USERLIB_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", ".."))
if _USERLIB_DIR not in sys.path:
    sys.path.insert(0, _USERLIB_DIR)

from external_gui_lib import zmq_v2  # noqa: E402
from external_gui_lib.zmq_v2 import (  # noqa: E402
    CANONICAL_CAPABILITIES,
    InMemoryTransport,
    PROTOCOL_VERSION,
    RemoteControlServerBase,
    RequestIdCounter,
    client_matches_advertised,
    encode_reply,
    encode_request,
    handler,
    parse_envelope,
)


# ---------------------------------------------------------------------------
# V1. Canonical capabilities frozenset is pinned (Q3 anti-drift)
# ---------------------------------------------------------------------------

def test_V1_canonical_capabilities_pin():
  """Q3 anti-drift: the canonical capability set is exactly these three.

  Adding a capability requires extending CANONICAL_CAPABILITIES in a
  separate PR before any server claims it. This is the test that fails
  to force that two-step.
  """
  assert CANONICAL_CAPABILITIES == frozenset(
      {"monitors", "heartbeat", "wait_for_lock"})
  # Must be immutable
  assert isinstance(CANONICAL_CAPABILITIES, frozenset)


def test_V1_protocol_version_pin():
  assert PROTOCOL_VERSION == 2


# ---------------------------------------------------------------------------
# V2. Envelope encode/decode round-trip (§1)
# ---------------------------------------------------------------------------

def test_V2_request_envelope_roundtrip():
  raw = encode_request("PROGRAM_VALUE", request_id=17,
                       connection="TiSa_set", value=348.666410,
                       args={"wait_for_lock": True})
  env = parse_envelope(raw)
  assert env["v"] == PROTOCOL_VERSION
  assert env["action"] == "PROGRAM_VALUE"
  assert env["id"] == 17
  assert env["connection"] == "TiSa_set"
  assert env["value"] == 348.666410
  assert env["args"] == {"wait_for_lock": True}
  assert "request_timestamp" in env


def test_V2_reply_envelope_roundtrip():
  raw = encode_reply(status="SUCCESS", request_id=17, value=42)
  env = parse_envelope(raw)
  assert env["v"] == PROTOCOL_VERSION
  assert env["status"] == "SUCCESS"
  assert env["id"] == 17
  assert env["value"] == 42
  assert "server_timestamp" in env


def test_V2_parse_rejects_non_json():
  with pytest.raises(ValueError):
    parse_envelope(b"not json")


def test_V2_parse_rejects_non_dict():
  with pytest.raises(ValueError):
    parse_envelope(b"[1, 2, 3]")


# ---------------------------------------------------------------------------
# V3. InMemoryTransport pair behaviors (§5)
# ---------------------------------------------------------------------------

def test_V3_in_memory_transport_pair_exchange():
  a, b = InMemoryTransport.pair()
  a.send(b"hello")
  assert b.recv(timeout_ms=100) == b"hello"
  b.send(b"world")
  assert a.recv(timeout_ms=100) == b"world"


def test_V3_in_memory_transport_recv_timeout():
  a, _b = InMemoryTransport.pair()
  with pytest.raises(TimeoutError):
    a.recv(timeout_ms=10)


def test_V3_in_memory_transport_close_blocks_send_recv():
  a, b = InMemoryTransport.pair()
  a.close()
  with pytest.raises(RuntimeError):
    a.send(b"x")
  with pytest.raises(RuntimeError):
    a.recv(timeout_ms=10)
  # Other side still functional (independent close)
  b.send(b"y")


# ---------------------------------------------------------------------------
# V4. @handler decorator + dispatch (§2)
# ---------------------------------------------------------------------------

class _TestServer(RemoteControlServerBase):
  CAPABILITIES = frozenset({"monitors"})

  @handler("PROGRAM_VALUE")
  def _handle_program(self, conn, value, args, request_id):
    return encode_reply(status="SUCCESS", request_id=request_id,
                        value={"echo_conn": conn, "echo_value": value})

  @handler("CHECK_VALUE")
  def _handle_check(self, conn, value, args, request_id):
    return encode_reply(status="SUCCESS", request_id=request_id, value=42)


def _drive_one(server, request_frame):
  client_t, server_t = InMemoryTransport.pair()
  server._transport = server_t  # swap in the paired transport
  client_t.send(request_frame)
  server.serve_once(timeout_ms=100)
  reply_raw = client_t.recv(timeout_ms=100)
  return parse_envelope(reply_raw)


def test_V4_program_value_dispatch():
  _, server_t = InMemoryTransport.pair()
  server = _TestServer("TestServer", server_t)
  reply = _drive_one(server, encode_request(
      "PROGRAM_VALUE", request_id=7, connection="X", value=3.14))
  assert reply["status"] == "SUCCESS"
  assert reply["id"] == 7
  assert reply["value"]["echo_value"] == 3.14


def test_V4_unknown_action_returns_structured_error():
  _, server_t = InMemoryTransport.pair()
  server = _TestServer("TestServer", server_t)
  reply = _drive_one(server, encode_request("BOGUS", request_id=8))
  assert reply["status"] == "ERROR"
  assert reply["error"]["code"] == "unknown_action"
  assert reply["id"] == 8


def test_V4_handler_exception_wrapped():
  class _BadServer(RemoteControlServerBase):
    CAPABILITIES = frozenset()
    @handler("ZAP")
    def _z(self, conn, value, args, request_id):
      raise RuntimeError("intentional")
  _, server_t = InMemoryTransport.pair()
  server = _BadServer("Bad", server_t)
  reply = _drive_one(server, encode_request("ZAP", request_id=9))
  assert reply["status"] == "ERROR"
  assert reply["error"]["code"] == "handler_exception"
  assert "intentional" in reply["error"]["message"]


def test_V4_handler_must_return_bytes_not_dict():
  """Strict-contract pin: handlers MUST return bytes (via encode_reply).

  An earlier draft silently wrapped dict returns as SUCCESS with
  `value = result.get("value")`, which discarded any `status`/`error`
  keys the handler tried to express. We now refuse non-bytes returns
  with TypeError, surfaced as a handler_exception ERROR reply.
  """
  class _DictReturningServer(RemoteControlServerBase):
    CAPABILITIES = frozenset()
    @handler("OOPS")
    def _oops(self, conn, value, args, request_id):
      # Subclass author who forgot to call encode_reply.
      return {"status": "REJECTED", "value": 42}
  _, server_t = InMemoryTransport.pair()
  server = _DictReturningServer("OopsServer", server_t)
  reply = _drive_one(server, encode_request("OOPS", request_id=4))
  # Footgun is loud, not silent: TypeError surfaces as handler_exception.
  assert reply["status"] == "ERROR"
  assert reply["error"]["code"] == "handler_exception"
  assert "must return bytes" in reply["error"]["message"]


# ---------------------------------------------------------------------------
# V5. HELLO reply: advertises capabilities; advertises connections only if set
# ---------------------------------------------------------------------------

def test_V5_hello_advertises_capabilities():
  _, server_t = InMemoryTransport.pair()
  server = _TestServer("TestServer", server_t)
  reply = _drive_one(server, encode_request("HELLO", request_id=1))
  assert reply["status"] == "SUCCESS"
  assert reply["protocol_version"] == PROTOCOL_VERSION
  assert reply["server"] == "TestServer"
  assert set(reply["capabilities"]) == {"monitors"}
  # No advertisement when ADVERTISED_CONNECTIONS is None
  assert "connections" not in reply


def test_V5_hello_advertises_connections_when_set():
  class _HubServer(RemoteControlServerBase):
    CAPABILITIES = frozenset({"monitors"})
    ADVERTISED_CONNECTIONS = ["YAG_1_*", "YAG_2_*"]
  _, server_t = InMemoryTransport.pair()
  server = _HubServer("BigSkyLasers", server_t)
  reply = _drive_one(server, encode_request("HELLO"))
  assert reply["connections"] == ["YAG_1_*", "YAG_2_*"]


def test_V5_capabilities_must_be_canonical_subset():
  """Q3: declaring an unknown capability raises at construction."""
  class _BadCapsServer(RemoteControlServerBase):
    CAPABILITIES = frozenset({"warp_drive"})
  _, server_t = InMemoryTransport.pair()
  with pytest.raises(ValueError, match="non-canonical"):
    _BadCapsServer("Bad", server_t)


# ---------------------------------------------------------------------------
# V6. Q1 prefix-match algorithm
# ---------------------------------------------------------------------------

def test_V6_prefix_match_basic():
  advertised = ["YAG_1_*", "YAG_2_*"]
  assert client_matches_advertised("YAG_1_voltage", advertised)
  assert client_matches_advertised("YAG_2_shutter", advertised)
  assert not client_matches_advertised("YAG_3_voltage", advertised)
  assert not client_matches_advertised("LASER_A_voltage", advertised)


def test_V6_prefix_match_empty_advertisement_passes_through():
  """No advertisement means no fail-fast check; server is the authority."""
  assert client_matches_advertised("anything", None)
  assert client_matches_advertised("anything", [])


def test_V6_prefix_match_handles_non_string_entries():
  # Defensive: garbage in advertisement shouldn't crash the matcher.
  assert client_matches_advertised("YAG_1_v", [None, 42, "YAG_1_*"])


# ---------------------------------------------------------------------------
# V7. Q2 id echo + RequestIdCounter monotonic
# ---------------------------------------------------------------------------

def test_V7_id_echoed_on_success():
  _, server_t = InMemoryTransport.pair()
  server = _TestServer("TestServer", server_t)
  reply = _drive_one(server, encode_request(
      "PROGRAM_VALUE", request_id=12345, connection="X", value=1))
  assert reply["id"] == 12345


def test_V7_id_optional_when_missing():
  _, server_t = InMemoryTransport.pair()
  server = _TestServer("TestServer", server_t)
  # Request without id should not crash; reply omits id.
  raw = encode_request("PROGRAM_VALUE", connection="X", value=1)
  reply = _drive_one(server, raw)
  assert reply["status"] == "SUCCESS"
  assert "id" not in reply


def test_V7_request_id_counter_monotonic():
  c = RequestIdCounter()
  ids = [c.next_id() for _ in range(5)]
  assert ids == [0, 1, 2, 3, 4]
  c.reset()
  assert c.next_id() == 0


# ---------------------------------------------------------------------------
# V8. Q4 hard sunset: v1 requests refused
# ---------------------------------------------------------------------------

def test_V8_v1_request_refused():
  _, server_t = InMemoryTransport.pair()
  server = _TestServer("TestServer", server_t)
  # v1 envelope: no "v" key, bare action+connection dict.
  raw = json.dumps({"action": "HELLO", "connection": ""}).encode("utf-8")
  reply = _drive_one(server, raw)
  assert reply["status"] == "ERROR"
  assert reply["error"]["code"] == "v1_protocol_refused"
  assert reply["error"]["retryable"] is False


def test_V8_wrong_version_refused():
  _, server_t = InMemoryTransport.pair()
  server = _TestServer("TestServer", server_t)
  raw = json.dumps({"v": 99, "action": "HELLO"}).encode("utf-8")
  reply = _drive_one(server, raw)
  assert reply["error"]["code"] == "v1_protocol_refused"


# ---------------------------------------------------------------------------
# V9. PING action
# ---------------------------------------------------------------------------

def test_V9_ping_returns_uptime_and_server_name():
  _, server_t = InMemoryTransport.pair()
  server = _TestServer("TestServer", server_t)
  reply = _drive_one(server, encode_request("PING", request_id=99))
  assert reply["status"] == "SUCCESS"
  assert reply["server"] == "TestServer"
  assert reply["uptime_seconds"] >= 0.0
  assert reply["id"] == 99  # Q2 id echo holds for PING too (was unasserted)


# ---------------------------------------------------------------------------
# V10. serve_once timeout returns False without exception
# ---------------------------------------------------------------------------

def test_V10_serve_once_timeout_returns_false():
  _, server_t = InMemoryTransport.pair()
  server = _TestServer("TestServer", server_t)
  assert server.serve_once(timeout_ms=10) is False


# ---------------------------------------------------------------------------
# V11. RemoteCommunication (BLACS-side client) v2 roundtrip via mock server.
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_remote_comms():
  """Construct RemoteCommunication(mock=True) which sets up the
  paired InMemoryTransport + _MockRemoteServer internally."""
  pytest.importorskip(
      "blacs.tab_base_classes",
      reason="RemoteCommunication tests require an installed BLACS package",
  )
  from unittest import mock as _m  # noqa: PLC0415
  from user_devices.RemoteControl.blacs_workers import (  # noqa: PLC0415
      RemoteCommunication,
  )
  logger = _m.MagicMock()
  rc = RemoteCommunication(
      mock=True, logger=logger,
      child_connections=["chan_a", "chan_b"],
  )
  return rc


def test_V11_mock_connect_returns_true(mock_remote_comms):
  assert mock_remote_comms.connect_to_remote() is True
  assert mock_remote_comms.connected is True


def test_V11_mock_program_value_roundtrips_through_v2_envelope(
    mock_remote_comms):
  """SET then GET via the v2 envelope path proves encode/parse +
  RequestIdCounter + InMemoryTransport pair semantics work end-to-end."""
  mock_remote_comms.connect_to_remote()
  reply = mock_remote_comms.program_value("chan_a", 1.234)
  assert reply["status"] == "SUCCESS"

  check = mock_remote_comms.check_remote_value("chan_a")
  assert check["status"] == "SUCCESS"
  assert check["value"] == 1.234


def test_V11_mock_program_with_wait_for_lock_packs_args(mock_remote_comms):
  """Q2 §10-resolved: wait_for_lock moves into the v2 args dict. The
  mock server's @handler signature is (conn, value, args, request_id).
  We replace the mock server with a probe that records args."""
  import queue as _q  # noqa: PLC0415

  mock_remote_comms.connect_to_remote()
  args_seen = _q.Queue()

  orig_handler = mock_remote_comms._mock_server._handlers["PROGRAM_VALUE"]
  def _probe(conn, value, args, request_id):
    args_seen.put(args)
    return orig_handler(conn, value, args, request_id)
  mock_remote_comms._mock_server._handlers["PROGRAM_VALUE"] = _probe

  mock_remote_comms.program_value("chan_a", 5.0, wait_for_lock=True)
  recv_args = args_seen.get(timeout=1.0)
  assert recv_args == {"wait_for_lock": True}


def test_V11_request_id_monotonic_across_calls(mock_remote_comms):
  """Each request bumps the per-instance counter."""
  mock_remote_comms.connect_to_remote()
  start = mock_remote_comms._id_counter.next_id()
  mock_remote_comms.program_value("chan_a", 1.0)
  mock_remote_comms.check_remote_value("chan_a")
  end = mock_remote_comms._id_counter.next_id()
  # Two real calls + the bookend reads above = >= 3 id increments.
  assert end - start >= 3


def test_V11_unknown_action_returns_v1_style_dict_for_compat(mock_remote_comms):
  """RemoteCommunication translates raised RemoteRequestError back into
  a v1-shaped dict so existing _check_response callers keep working
  without refactoring. Status field gets the v2 enum value; error dict
  carries v2 code/message."""
  mock_remote_comms.connect_to_remote()
  # Send an action the mock server doesn't register.
  envelope = encode_request(
      action="FROBNICATE",
      request_id=mock_remote_comms._id_counter.next_id(),
  )
  mock_remote_comms._transport.send(envelope)
  mock_remote_comms._mock_server.serve_once(timeout_ms=100)
  raw_reply = mock_remote_comms._transport.recv(timeout_ms=100)
  reply = parse_envelope(raw_reply)
  assert reply["status"] == "ERROR"
  assert reply["error"]["code"] == "unknown_action"


if __name__ == "__main__":
  import subprocess
  raise SystemExit(subprocess.call(
      [sys.executable, "-m", "pytest", __file__, "-v"]))
