"""Reply-side protocol-version gate.

Version enforcement used to be one-directional (server refuses v1 requests,
client trusts any reply), so a parent-only cutover made every setpoint against
a still-v1 GUI die on a misleading 5s timeout. Pin the real diagnosis.

SDK-free: no sockets — inject an InMemoryTransport side and pre-seed the reply.
"""
import json
import logging

import pytest

from external_gui_lib.zmq_v2 import InMemoryTransport
from user_devices.RemoteControl.blacs_workers import (
    RemoteCommunication,
    RemoteRequestError,
)


def _comms_with_seeded_reply(reply_dict):
    comms = RemoteCommunication(
        host="127.0.0.1", port=1, logger=logging.getLogger("test_reply_version_gate"))
    client_t, server_t = InMemoryTransport.pair()
    comms._transport = client_t
    server_t.send(json.dumps(reply_dict).encode("utf-8"))
    return comms


@pytest.mark.parametrize("reply", [
    {"status": "SUCCESS", "value": 348.686},           # v1: no version field
    {"v": 1, "status": "SUCCESS", "value": 348.686},   # explicit v1
])
def test_raw_request_rejects_non_v2_reply(reply):
    comms = _comms_with_seeded_reply(reply)
    with pytest.raises(RemoteRequestError) as exc:
        comms._raw_request("CHECK_VALUE", connection="1")
    assert exc.value.code == "protocol_version_mismatch"
    assert "still on v1" in exc.value.message


def test_raw_request_accepts_v2_reply():
    comms = _comms_with_seeded_reply({"v": 2, "status": "SUCCESS", "value": 348.686})
    assert comms._raw_request("CHECK_VALUE", connection="1")["value"] == 348.686
