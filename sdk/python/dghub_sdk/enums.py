"""DGHub SDK 全局使用的枚举类型。"""

from enum import StrEnum


class OpCode(StrEnum):
    """WebSocket 协议操作码。

    包含客户端到服务端与服务端到客户端的消息类型。
    """

    # 客户端 -> 服务端
    HELLO = "hello"
    TRIGGER = "trigger"
    EVENT = "event"
    PULSE = "pulse"
    SET_STRENGTH = "set_strength"
    ADJUST_STRENGTH = "adjust_strength"
    STATUS = "status"
    LOG = "log"
    SET_CONFIG = "set_config"
    # 服务端 -> 客户端
    HELLO_ACK = "hello_ack"
    CONFIG = "config"
    CONFIG_CHANGED = "config_changed"
    DEVICE_INFO = "device_info"
    STOP = "stop"
    PING = "ping"
    PONG = "pong"


class Channel(StrEnum):
    """强度/波形指令的目标设备通道。"""

    A = "a"
    B = "b"
    BOTH = "both"


class Action(StrEnum):
    """触发动作类型 —— 指定作用于设备的哪些方面。"""

    BOTH = "both"
    """同时作用于强度和波形。"""
    STRENGTH = "strength"
    """仅作用于强度。"""
    WAVEFORM = "waveform"
    """仅作用于波形。"""


class StrengthMode(StrEnum):
    """触发对 baseline 强度的作用方式。

    ROLLBACK：临时偏移强度，持续时间结束后自动恢复。
    PERMANENT：永久偏移 baseline（持久化到配置）。
    """

    ROLLBACK = "rollback"
    PERMANENT = "permanent"


class LogLevel(StrEnum):
    """send_log 消息的日志级别。"""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class CheckState(StrEnum):
    """通过 send_status 上报的启动检查状态值。"""

    IDLE = "idle"
    """尚未开始或无数据。"""
    PENDING = "pending"
    """检查进行中。"""
    OK = "ok"
    """检查通过。"""
    WARN = "warn"
    """检查完成但有警告。"""
    FAIL = "fail"
    """检查失败。"""


class DeviceType(StrEnum):
    """当前连接的 DGLab 设备硬件版本。"""

    V2 = "v2"
    V3 = "v3"
    V4 = "v4"
    UNKNOWN = ""
