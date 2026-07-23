"""DGHub SDK — runtime library for DGHub plugin development.

Usage:
    from dghub_sdk import Agent, Codec, OpCode, ...

    with Agent(on_config=on_config, on_stop=on_stop) as agent:
        while running:
            agent.poll()
            while exc := agent.get_exception():
                raise exc
"""

from .agent import Agent
from .codec import Codec, CodecMessage
from .enums import (
    Action, Channel, CheckState, DeviceType,
    LogLevel, OpCode, StrengthMode,
)

__all__ = [
    "Agent",
    "Codec",
    "CodecMessage",
    "Action",
    "Channel",
    "CheckState",
    "DeviceType",
    "LogLevel",
    "OpCode",
    "StrengthMode",
]

__version__ = "0.1.0"
