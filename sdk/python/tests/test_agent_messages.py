import json
from pathlib import Path

from dghub_sdk import Action, Agent, Channel


def test_agent_send_helpers_expose_sdk_1_1_fields(tmp_path: Path) -> None:
    agent = Agent(manifest_dir=tmp_path)
    sent: list[str] = []
    agent._schedule_send = sent.append

    agent.send_trigger(
        action=Action.STRENGTH,
        name="BOSS 重击",
        cause="生命值下降",
        pulse_name="短促",
        target_id="target-1",
    )
    agent.send_event(
        "受击",
        "BOSS 重击",
        cause="生命值下降",
        pulse_name="短促",
        from_pct=20,
        to_pct=40,
        delta_pct=20,
        target_id="target-1",
    )
    agent.send_pulse("短促", Channel.A, target_id="target-1")
    agent.send_set_strength(Channel.A, 30, target_id="target-1")
    agent.send_adjust_strength(Channel.B, -10, target_id="target-1")

    payloads = [json.loads(raw) for raw in sent]
    assert [payload["target_id"] for payload in payloads] == ["target-1"] * 5
    assert payloads[0]["name"] == "BOSS 重击"
    assert payloads[0]["cause"] == "生命值下降"
    assert payloads[0]["pulse_name"] == "短促"
    assert payloads[1]["from_pct"] == 20
    assert payloads[1]["to_pct"] == 40
    assert payloads[1]["delta_pct"] == 20
