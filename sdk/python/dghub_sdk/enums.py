"""Enum types used throughout the DGHub SDK."""

from enum import StrEnum


class OpCode(StrEnum):
    """WebSocket protocol operation codes.

    Client-to-server and server-to-client message types.
    """

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
    """Target device channel for strength/waveform commands."""

    A = "a"
    B = "b"
    BOTH = "both"


class Action(StrEnum):
    """Trigger action type — what aspects of the device to affect."""

    BOTH = "both"
    """Affect both strength and waveform."""
    STRENGTH = "strength"
    """Affect strength only."""
    WAVEFORM = "waveform"
    """Affect waveform only."""


class StrengthMode(StrEnum):
    """How a trigger affects the baseline strength.

    ROLLBACK: temporarily offset strength, auto-revert after duration.
    PERMANENT: permanently shift baseline (persisted to config).
    """

    ROLLBACK = "rollback"
    PERMANENT = "permanent"


class LogLevel(StrEnum):
    """Log severity levels for send_log messages."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class CheckState(StrEnum):
    """Startup-check status values reported via send_status."""

    IDLE = "idle"
    """Not yet started or no data."""
    PENDING = "pending"
    """Check in progress."""
    OK = "ok"
    """Check passed."""
    WARN = "warn"
    """Check completed with warnings."""
    FAIL = "fail"
    """Check failed."""


class DeviceType(StrEnum):
    """Connected DGLab device hardware version."""

    V2 = "v2"
    V3 = "v3"
    UNKNOWN = ""
