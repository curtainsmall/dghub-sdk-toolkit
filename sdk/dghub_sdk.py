"""DGHub SDK — single-file runtime library for DGHub plugin development.

Usage:
    from dghub_sdk import Agent, Codec, OpCode, ...

    with Agent(on_config=on_config, on_stop=on_stop) as agent:
        while running:
            agent.poll()
            while exc := agent.get_exception():
                raise exc
"""

import asyncio
import json
import logging
import os
import queue
import sys
import threading
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


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
                # hello_ack carries accepted/reason/sdk_version
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


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class Agent:
    """Async WebSocket connection manager — fully sync public API.

    Wraps the entire async lifecycle in a background thread. Messages received
    from the server are queued and dispatched to callbacks when ``poll()`` is
    called from the user's thread.
    """

    def __init__(
        self,
        *,
        manifest_dir: Path | None = None,
        max_retries: int = 5,
        send_timeout: float | None = None,
        on_ready: Callable[[dict[str, Any]], None] | None = None,
        on_config: Callable[[dict[str, Any]], None] | None = None,
        on_config_changed: Callable[[str, Any], None] | None = None,
        on_device_info: Callable[[bool, DeviceType, int, int], None] | None = None,
        on_stop: Callable[[str], None] | None = None,
        on_ping: Callable[[float], None] | None = None,
    ):
        # --- manifest resolution ---
        if manifest_dir is None:
            # default to caller's file directory
            caller_file = sys._getframe(1).f_code.co_filename
            self._manifest_dir = Path(caller_file).resolve().parent
        else:
            self._manifest_dir = Path(manifest_dir)
            if not self._manifest_dir.is_absolute():
                caller_file = sys._getframe(1).f_code.co_filename
                base = Path(caller_file).resolve().parent
                self._manifest_dir = (base / self._manifest_dir).resolve()

        self._max_retries = max_retries
        self._send_timeout = send_timeout

        # --- callbacks ---
        self.on_ready = on_ready
        self.on_config = on_config
        self.on_config_changed = on_config_changed
        self.on_device_info = on_device_info
        self.on_stop = on_stop
        self.on_ping = on_ping

        # --- internal state ---
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ws: Any = None
        self._token: str = ""
        self._manifest: dict[str, Any] = {}
        self._plugin_id: str = ""
        self._connected = False
        self._stopped = False

        # queues (thread-safe)
        self._queue: queue.Queue[CodecMessage] = queue.Queue()
        self._error_queue: queue.Queue[Exception] = queue.Queue()

    # -- properties --------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def plugin_id(self) -> str:
        return self._plugin_id

    # -- public lifecycle --------------------------------------------------

    def start(self) -> None:
        """Launch WebSocket connection in a background thread. Non-blocking."""
        self._stopped = False
        self._thread = threading.Thread(target=self._run_async, daemon=True)
        self._thread.start()

    def poll(self, timeout: float | None = None) -> None:
        """Process received messages. Invokes callbacks on current thread.

        ``timeout=None`` (default): non-blocking, drain all queued messages.
        ``timeout>=0``: blocking, wait up to *timeout* seconds for a message.
        """
        if timeout is None:
            while not self._queue.empty():
                msg = self._queue.get_nowait()
                self._invoke(msg)
        else:
            try:
                msg = self._queue.get(timeout=timeout)
                self._invoke(msg)
            except queue.Empty:
                pass

    def stop(self) -> None:
        """Signal the background loop to stop and disconnect."""
        self._stopped = True
        if self._loop is not None and self._loop.is_running():
            async def _do_close():
                if self._ws is not None:
                    await self._ws.close()
                    self._ws = None
            asyncio.run_coroutine_threadsafe(_do_close(), self._loop)

    def wait(self, timeout: float | None = None) -> None:
        """Block until the background thread exits (optional)."""
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def __enter__(self) -> "Agent":
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()
        self.wait()

    # -- public send methods (all sync) ------------------------------------

    def send(self, raw: str) -> None:
        """Send a raw JSON string over the WebSocket."""
        self._schedule_send(raw)

    def send_trigger(
        self,
        action: Action = Action.BOTH,
        delta_pct: int = 0,
        strength_mode: StrengthMode = StrengthMode.ROLLBACK,
        duration_s: float = 1.0,
        preset: str = "",
        channel: Channel = Channel.BOTH,
        label: str | None = None,
        username: str | None = None,
    ) -> None:
        raw = Codec.trigger(action, delta_pct, strength_mode,
                            duration_s, preset, channel, label, username)
        self._schedule_send(raw)

    def send_event(
        self,
        label: str,
        name: str,
        username: str | None = None,
        strength_pct: int | None = None,
        duration: float = 1.0,
        event_id: str | None = None,
    ) -> None:
        raw = Codec.event(label, name, username, strength_pct, duration, event_id)
        self._schedule_send(raw)

    def send_pulse(self, preset: str, channel: Channel = Channel.BOTH) -> None:
        raw = Codec.pulse(preset, channel)
        self._schedule_send(raw)

    def send_strength(self, channel: Channel, pct: int) -> None:
        raw = Codec.set_strength(channel, pct)
        self._schedule_send(raw)

    def send_adjust_strength(self, channel: Channel, delta_pct: int) -> None:
        raw = Codec.adjust_strength(channel, delta_pct)
        self._schedule_send(raw)

    def send_status(self, fields: dict[str, Any]) -> None:
        raw = Codec.status(fields)
        self._schedule_send(raw)

    def send_log(self, level: LogLevel, message: str) -> None:
        raw = Codec.log(level, message)
        self._schedule_send(raw)

    def send_set_config(self, key: str, value: Any) -> None:
        raw = Codec.set_config(key, value)
        self._schedule_send(raw)

    # -- public error inspection -------------------------------------------

    def get_exception(self) -> Exception | None:
        """Return one captured exception from the background thread, or ``None``.

        Multiple exceptions are preserved in an internal queue. The caller
        should loop until ``None`` is returned.
        """
        try:
            return self._error_queue.get_nowait()
        except queue.Empty:
            return None

    # -- internal: thread entry point --------------------------------------

    def _run_async(self) -> None:
        """Background thread entry point. Creates its own event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect_and_loop())
        except Exception as exc:
            self._error_queue.put(exc)
        finally:
            self._loop.close()
            self._loop = None

    async def _connect_and_loop(self) -> None:
        """Core async lifecycle: load manifest, connect, handshake, receive loop."""
        import websockets

        # ---- resolve manifest ----
        manifest_path = self._manifest_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"manifest.json not found: {manifest_path}")
        with open(manifest_path, "r", encoding="utf-8") as f:
            self._manifest = json.loads(f.read())

        self._plugin_id = self._manifest.get("id", "")

        # ---- env vars ----
        host = os.environ.get("DGHUB_HOST", "localhost")
        port = os.environ.get("DGHUB_PORT", "27020")
        self._token = os.environ.get("DGHUB_TOKEN", "")
        if not self._token:
            raise ValueError("DGHUB_TOKEN environment variable is not set")

        url = f"ws://{host}:{port}/ws/plugin?token={self._token}"

        # ---- connect with retry ----
        for attempt in range(self._max_retries + 1):
            try:
                self._ws = await websockets.connect(url)
                break
            except (ConnectionRefusedError, TimeoutError, OSError) as exc:
                if attempt < self._max_retries:
                    delay = min(2 ** attempt, 30)
                    await asyncio.sleep(delay)
                else:
                    raise

        # ---- handshake ----
        hello_raw = Codec.hello(self._token, self._manifest)
        await self._ws.send(hello_raw)
        ack_raw = await self._ws.recv()
        ack = json.loads(ack_raw)

        if not ack.get("accepted", False):
            raise ConnectionError(
                f"hello rejected: {ack.get('reason', 'unknown')}"
            )

        self._connected = True
        self._queue.put(CodecMessage(op=OpCode.HELLO_ACK, data={
            "accepted": ack.get("accepted"),
            "reason": ack.get("reason"),
            "sdk_version": ack.get("sdk_version"),
        }))

        # ---- receive loop ----
        async for raw in self._ws:
            if self._stopped:
                break
            msg = Codec.parse(raw)
            if msg.op == OpCode.PING:
                # auto-respond pong in background thread
                pong = json.dumps({"op": "pong", "t": msg.t})
                await self._ws.send(pong)
                self._queue.put(msg)
            else:
                self._queue.put(msg)
                if msg.op == OpCode.STOP:
                    break

        self._connected = False

    # -- internal: helper methods ------------------------------------------

    def _invoke(self, msg: CodecMessage) -> None:
        """Dispatch a single message to the appropriate callback."""
        match msg.op:
            case OpCode.HELLO_ACK:
                if self.on_ready and msg.data:
                    self.on_ready(msg.data)
            case OpCode.CONFIG:
                if self.on_config:
                    self.on_config(msg.data or {})
            case OpCode.CONFIG_CHANGED:
                if self.on_config_changed:
                    self.on_config_changed(msg.key or "", msg.value)
            case OpCode.DEVICE_INFO:
                if self.on_device_info and all(
                    v is not None for v in (
                        msg.connected, msg.device_type,
                        msg.max_strength_a, msg.max_strength_b,
                    )
                ):
                    self.on_device_info(
                        msg.connected, msg.device_type,
                        msg.max_strength_a, msg.max_strength_b,
                    )
            case OpCode.STOP:
                if self.on_stop:
                    self.on_stop(msg.reason or "")
            case OpCode.PING:
                if self.on_ping:
                    self.on_ping(msg.t or 0.0)
            case _:
                pass

    def _schedule_send(self, raw: str) -> None:
        """Schedule sending a message on the background event loop."""
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError("Agent is not connected")

        async def _do_send():
            if self._ws is not None:
                await self._ws.send(raw)

        future = asyncio.run_coroutine_threadsafe(_do_send(), self._loop)
        if self._send_timeout is not None:
            future.result(timeout=self._send_timeout)
