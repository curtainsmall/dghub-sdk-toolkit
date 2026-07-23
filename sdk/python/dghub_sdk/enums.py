"""Enum types used throughout the DGHub SDK."""

from enum import StrEnum


class OpCode(StrEnum):
    # Client -> Server
    HELLO = "hello"
    TRIGGER = "trigger"
    EVENT = "event"
    PULSE = "pulse"
    SET_STRENGTH = "set_strength"
    ADJUST_STRENGTH = "adjust_strength"
    STATUS = "status"
    LOG = "log"
    SET_CONFIG = "set_config"
    # Server -> Client
    HELLO_ACK = "hello_ack"
    CONFIG = "config"
    CONFIG_CHANGED = "config_changed"
    DEVICE_INFO = "device_info"
    STOP = "stop"
    PING = "ping"
    PONG = "pong"


class Channel(StrEnum):
    A = "a"
    B = "b"
    BOTH = "both"


class Action(StrEnum):
    BOTH = "both"
    STRENGTH = "strength"
    WAVEFORM = "waveform"


class StrengthMode(StrEnum):
    ROLLBACK = "rollback"
    PERMANENT = "permanent"


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class CheckState(StrEnum):
    IDLE = "idle"
    PENDING = "pending"
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


class DeviceType(StrEnum):
    V2 = "v2"
    V3 = "v3"
    UNKNOWN = ""
