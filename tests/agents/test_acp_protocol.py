from pms.agents.acp.protocol import ACPMessageType, ACPProtocol


def test_acp_protocol_request_roundtrip():
    protocol = ACPProtocol()
    request_id, payload = protocol.create_request("session/prompt", {"foo": "bar"})
    parsed = protocol.parse_message(payload)

    assert parsed["type"] is ACPMessageType.REQUEST
    assert parsed["id"] == request_id
    assert parsed["method"] == "session/prompt"
    assert parsed["params"]["foo"] == "bar"


def test_acp_protocol_notification_roundtrip():
    protocol = ACPProtocol()
    payload = protocol.create_notification(
        "session/update", {"kind": "agent_message_chunk"}
    )
    parsed = protocol.parse_message(payload)

    assert parsed["type"] is ACPMessageType.NOTIFICATION
    assert parsed["method"] == "session/update"


def test_acp_protocol_response_roundtrip():
    protocol = ACPProtocol()
    payload = protocol.create_response(10, {"ok": True})
    parsed = protocol.parse_message(payload)

    assert parsed["type"] is ACPMessageType.RESPONSE
    assert parsed["id"] == 10
    assert parsed["result"]["ok"] is True


def test_acp_protocol_parse_error():
    protocol = ACPProtocol()
    parsed = protocol.parse_message("{not json")

    assert parsed["type"] is ACPMessageType.PARSE_ERROR
