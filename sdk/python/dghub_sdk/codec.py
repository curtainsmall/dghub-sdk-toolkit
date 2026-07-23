"""Message dataclass and codec (serialization / deserialization)."""

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .enums import Action, Channel, DeviceType, LogLevel, OpCode, StrengthMode


# ---------------------------------------------------------------------------
# CodecMessage
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CodecMessage:
    """Typed result of Codec.parse(). Check ``.op`` to know which fields are populated."""
    op: OpCode
    # hello_ack
    status: str | None = None
    # config
    data: dict[str, Any] | None = None
    # config_changed
    key: str | None = None
    value: bool | int | str | None = None
    # device_info
    connected: bool | None = None
    device_type: DeviceType | None = None
    max_strength_a: int | None = None
    max_strength_b: int | None = None
    # stop
    reason: str | None = None
    # ping
    t: float | None = None


# ---------------------------------------------------------------------------
# Codec (namespace class)
# ---------------------------------------------------------------------------


class Codec:
    """Namespace for all message encoding/decoding. No instantiation needed."""

    @staticmethod
    def hello(token: str, manifest: dict[str, Any]) -> str:
        """Build hello handshake message."""
        if not token:
            raise ValueError("token is required")
        if not isinstance(manifest, dict):
            raise TypeError("manifest must be a dict")
        return json.dumps({
            "op": "hello",
            "token": token,
            "manifest": manifest,
        })

    @staticmethod
    def trigger(
        action: Action = Action.BOTH,
        delta_pct: int = 0,
        strength_mode: StrengthMode = StrengthMode.ROLLBACK,
        duration_s: float = 1.0,
        preset: str = "",
        channel: Channel = Channel.BOTH,
        label: str | None = None,
        username: str | None = None,
    ) -> str:
        """Build unified trigger message.

        Raises ``ValueError`` if ``preset`` is empty when ``action``
        includes waveform (Action.BOTH or Action.WAVEFORM).
        """
        if action in (Action.BOTH, Action.WAVEFORM) and not preset:
            raise ValueError("preset is required when action includes waveform")
        msg: dict[str, Any] = {
            "op": "trigger",
            "action": action.value,
            "delta_pct": delta_pct,
            "strength_mode": strength_mode.value,
            "duration_s": duration_s,
            "preset": preset,
            "channel": channel.value,
        }
        if label is not None:
            msg["label"] = label
        if username is not None:
            msg["username"] = username
        return json.dumps(msg)

    @staticmethod
    def event(
        label: str,
        name: str,
        username: str | None = None,
        strength_pct: int | None = None,
        duration: float = 1.0,
        event_id: str | None = None,
    ) -> str:
        """Build one-time event message."""
        if not label:
            raise ValueError("label is required")
        if not name:
            raise ValueError("name is required")
        msg: dict[str, Any] = {
            "op": "event",
            "label": label,
            "name": name,
            "duration": duration,
        }
        if username is not None:
            msg["username"] = username
        if strength_pct is not None:
            msg["strength_pct"] = strength_pct
        if event_id is not None:
            msg["event_id"] = event_id
        return json.dumps(msg)

    @staticmethod
    def pulse(preset: str, channel: Channel = Channel.BOTH) -> str:
        """Build waveform-only pulse message."""
        if not preset:
            raise ValueError("preset is required")
        return json.dumps({
            "op": "pulse",
            "preset": preset,
            "channel": channel.value,
        })

    @staticmethod
    def set_strength(channel: Channel, pct: int) -> str:
        """Build set_strength message."""
        if not 0 <= pct <= 100:
            raise ValueError("pct must be 0-100")
        return json.dumps({
            "op": "set_strength",
            "channel": channel.value,
            "pct": pct,
        })

    @staticmethod
    def adjust_strength(channel: Channel, delta_pct: int) -> str:
        """Build adjust_strength message."""
        if not -100 <= delta_pct <= 100:
            raise ValueError("delta_pct must be -100 to 100")
        return json.dumps({
            "op": "adjust_strength",
            "channel": channel.value,
            "delta_pct": delta_pct,
        })

    @staticmethod
    def status(fields: dict[str, Any]) -> str:
        """Build status update message."""
        if not isinstance(fields, dict):
            raise TypeError("fields must be a dict")
        return json.dumps({
            "op": "status",
            "fields": fields,
        })

    @staticmethod
    def log(level: LogLevel, message: str) -> str:
        """Build log message."""
        return json.dumps({
            "op": "log",
            "level": level.value,
            "message": message,
        })

    @staticmethod
    def set_config(key: str, value: Any) -> str:
        """Build set_config message for persisting runtime data."""
        return json.dumps({
            "op": "set_config",
            "key": key,
            "value": value,
        })

    @staticmethod
    def parse(raw: str) -> CodecMessage:
        """Parse JSON string into typed ``CodecMessage`` dataclass."""
        data = json.loads(raw)
        match data:
            case {"op": "hello_ack"} as ack:
                ack_fields = {k: v for k, v in ack.items() if k != "op"}
                return CodecMessage(op=OpCode.HELLO_ACK, data=ack_fields)
            case {"op": "config", "data": d}:
                return CodecMessage(op=OpCode.CONFIG, data=d)
            case {"op": "config_changed", "key": k, "value": v}:
                return CodecMessage(op=OpCode.CONFIG_CHANGED, key=k, value=v)
            case {"op": "device_info", "connected": c,
                  "device_type": dt, "max_strength_a": ma, "max_strength_b": mb}:
                return CodecMessage(
                    op=OpCode.DEVICE_INFO, connected=c,
                    device_type=DeviceType(dt),
                    max_strength_a=ma, max_strength_b=mb,
                )
            case {"op": "ping", "t": t}:
                return CodecMessage(op=OpCode.PING, t=t)
            case {"op": "stop", "reason": r}:
                return CodecMessage(op=OpCode.STOP, reason=r)
            case _:
                raise ValueError(f"Unknown op: {data.get('op')}")

    @staticmethod
    def serialize(msg: CodecMessage) -> str:
        """Serialize ``CodecMessage`` back to JSON string."""
        data: dict[str, Any] = {"op": msg.op.value}
        for key in ("status", "data", "key", "value", "connected",
                     "device_type", "max_strength_a", "max_strength_b",
                     "reason", "t"):
            val = getattr(msg, key)
            if val is not None:
                data[key] = val.value if isinstance(val, StrEnum) else val
        return json.dumps(data)
