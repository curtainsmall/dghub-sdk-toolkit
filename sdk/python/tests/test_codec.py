import json

import pytest

from dghub_sdk import Action, Channel, Codec, DeviceType


def _payload(raw: str) -> dict:
    return json.loads(raw)


def test_parse_accepts_v4_device_info() -> None:
    message = Codec.parse(json.dumps({
        "op": "device_info",
        "connected": True,
        "device_type": "v4",
        "max_strength_a": 100,
        "max_strength_b": 100,
    }))

    assert message.device_type is DeviceType.V4


def test_trigger_serializes_sdk_1_1_metadata_and_target() -> None:
    message = _payload(Codec.trigger(
        action=Action.STRENGTH,
        delta_pct=25,
        label="受击",
        username="player",
        name="BOSS 重击",
        cause="生命值下降",
        pulse_name="短促",
        target_id="target-1",
    ))

    assert message["name"] == "BOSS 重击"
    assert message["cause"] == "生命值下降"
    assert message["pulse_name"] == "短促"
    assert message["target_id"] == "target-1"


def test_event_serializes_sdk_1_1_metadata_and_target() -> None:
    message = _payload(Codec.event(
        label="受击",
        name="BOSS 重击",
        username="player",
        strength_pct=40,
        cause="生命值下降",
        pulse_name="短促",
        from_pct=20,
        to_pct=40,
        delta_pct=20,
        target_id="target-1",
    ))

    assert message["cause"] == "生命值下降"
    assert message["pulse_name"] == "短促"
    assert message["from_pct"] == 20
    assert message["to_pct"] == 40
    assert message["delta_pct"] == 20
    assert message["target_id"] == "target-1"


@pytest.mark.parametrize(
    "message",
    [
        lambda: Codec.pulse("短促", Channel.A, target_id="target-1"),
        lambda: Codec.set_strength(Channel.A, 30, target_id="target-1"),
        lambda: Codec.adjust_strength(Channel.B, -10, target_id="target-1"),
    ],
)
def test_device_commands_serialize_explicit_target(message) -> None:
    assert _payload(message())["target_id"] == "target-1"


def test_optional_target_is_omitted_for_older_hosts() -> None:
    message = _payload(Codec.pulse("短促", target_id=None))

    assert "target_id" not in message
