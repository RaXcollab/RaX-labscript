"""Canonical invariants for the v2 RemoteControl protocol foundation.

Tests use ``InMemoryTransport.pair()`` to avoid binding sockets. This is
the V1-V10 invariant pin set; future userlib worker tests (item 2.8c)
will build on the same pattern.

Run::

    cd c:/Users/radmo/labscript-suite/userlib/external_gui_lib
    python -m pytest tests/ -v

Should pass in any conda env that has pytest + the standard library
(no pyzmq dependency for these tests).
"""
from __future__ import annotations

import json
import sys

import pytest

sys.path.insert(0, "..")

from userlib.external_gui_lib import zmq_v2  # noqa: E402
from userlib.external_gui_lib.zmq_v2 import (  # noqa: E402
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


# ---------------------------------------------------------------------------
# V10. serve_once timeout returns False without exception
# ---------------------------------------------------------------------------

def test_V10_serve_once_timeout_returns_false():
  _, server_t = InMemoryTransport.pair()
  server = _TestServer("TestServer", server_t)
  assert server.serve_once(timeout_ms=10) is False


if __name__ == "__main__":
  import subprocess
  raise SystemExit(subprocess.call(
      [sys.executable, "-m", "pytest", __file__, "-v"]))
