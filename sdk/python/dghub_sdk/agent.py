"""Async WebSocket connection manager — fully sync public API.

Wraps the entire async lifecycle in a background thread. Messages received
from the server are queued and dispatched to callbacks when ``poll()`` is
called from the user's thread.
"""

import asyncio
import json
import os
import queue
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from .codec import Codec, CodecMessage
from .enums import Action, Channel, CheckState, DeviceType, LogLevel, OpCode, StrengthMode


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
        """Initialize the Agent.

        Args:
            manifest_dir: Directory containing ``manifest.json``. Defaults to
                the caller's file directory.
            max_retries: Maximum WebSocket connection retry attempts.
            send_timeout: Optional timeout (seconds) for each send operation.
                ``None`` means fire-and-forget (no blocking wait).
            on_ready: Called after successful handshake with hello_ack data.
            on_config: Called with the full config dict (pushed once after
                handshake). Signature: ``(config: dict) -> None``.
            on_config_changed: Called when a single config key changes.
                Signature: ``(key: str, value: Any) -> None``.
            on_device_info: Called on device state changes.
                Signature: ``(connected, device_type, max_a, max_b) -> None``.
            on_stop: Called when the server requests plugin shutdown.
                Signature: ``(reason: str) -> None``.
            on_ping: Called on server ping with timestamp.
        """
        # --- manifest resolution ---
        if manifest_dir is None:
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

        # startup-check state
        self._check_title: str = "Startup Check"
        self._check_steps: dict[str, dict] = {}

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
        """Send a strength/waveform trigger to the device.

        Args:
            action: What to affect — strength, waveform, or both.
            delta_pct: Strength change relative to baseline (0–100).
            strength_mode: ROLLBACK (temporary) or PERMANENT (persisted).
            duration_s: Trigger duration in seconds.
            preset: Waveform preset name (required if action includes waveform).
            channel: Target channel (a / b / both).
            label: Optional display label for the trigger event.
            username: Optional username associated with this trigger.

        Raises:
            ValueError: If action includes waveform but preset is empty.
        """
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
        """Send a one-time named event.

        Args:
            label: Event category label (required).
            name: Event display name (required).
            username: Optional username who triggered the event.
            strength_pct: Optional strength hint (0–100).
            duration: Event duration in seconds.
            event_id: Optional deduplication ID.
        """
        raw = Codec.event(label, name, username, strength_pct, duration, event_id)
        self._schedule_send(raw)

    def send_pulse(self, preset: str, channel: Channel = Channel.BOTH) -> None:
        """Send a waveform-only pulse (no strength change).

        Args:
            preset: Waveform preset name.
            channel: Target channel.
        """
        raw = Codec.pulse(preset, channel)
        self._schedule_send(raw)

    def send_set_strength(self, channel: Channel, pct: int) -> None:
        """Set absolute strength for a channel.

        Args:
            channel: Target channel.
            pct: Absolute strength percentage (0–100).
        """
        raw = Codec.set_strength(channel, pct)
        self._schedule_send(raw)

    def send_adjust_strength(self, channel: Channel, delta_pct: int) -> None:
        """Adjust strength by a relative delta.

        Args:
            channel: Target channel.
            delta_pct: Relative change (-100 to 100).
        """
        raw = Codec.adjust_strength(channel, delta_pct)
        self._schedule_send(raw)

    def send_status(self, fields: dict[str, Any]) -> None:
        """Report plugin status to the server (e.g. startup_check results).

        Args:
            fields: Key-value pairs of status data. Typically includes
                ``startup_check`` with a ``CheckState`` value.
        """
        raw = Codec.status(fields)
        self._schedule_send(raw)

    def send_log(self, level: LogLevel, message: str) -> None:
        """Send a log message to the server for display in the DGHub console.

        Args:
            level: Severity level (debug/info/warning/error).
            message: Log message text.
        """
        raw = Codec.log(level, message)
        self._schedule_send(raw)

    def send_startup_check(
        self,
        key: str,
        title: str,
        state: CheckState,
        *,
        detail: str | None = None,
        hint: str | None = None,
        display_status: str | None = None,
        dont_send: bool = False,
    ) -> None:
        """Update a startup-check step and optionally send the full state.

        Maintains steps internally (keyed by ``key``). Each call upserts
        the step. Unless ``dont_send=True``, immediately sends all steps.

        Args:
            key: Unique step identifier.
            title: Human-readable step name.
            state: Current check state.
            detail: Optional status detail text.
            hint: Optional user-facing hint.
            display_status: Optionally set display_status in the same message.
            dont_send: If True, only update internal state without sending.
        """
        step: dict[str, Any] = {"key": key, "title": title, "state": state.value}
        if detail is not None:
            step["detail"] = detail
        if hint is not None:
            step["hint"] = hint
        self._check_steps[key] = step

        if dont_send:
            return

        fields: dict[str, Any] = {}
        if display_status is not None:
            fields["display_status"] = display_status
        fields["startup_check"] = {
            "title": self._check_title,
            "steps": list(self._check_steps.values()),
        }
        self.send_status(fields)

    def set_startup_check_title(self, title: str) -> None:
        """Set the startup-check panel title (does not send)."""
        self._check_title = title

    def send_display_status(self, text: str) -> None:
        """Send a display_status update to the server."""
        self.send_status({"display_status": text})

    def send_status_field(self, key: str, value: Any) -> None:
        """Send a single status field to the server.

        Args:
            key: Status field name.
            value: Field value (must be JSON-serializable).
        """
        self.send_status({key: value})

    def send_set_config(self, key: str, value: Any) -> None:
        """Persist a plugin-owned config key to the server.

        Use this to save runtime state that should survive restarts.
        Do not write server-reserved keys (e.g. ``target_id``).

        Args:
            key: Config key name.
            value: Value to persist (must be JSON-serializable).
        """
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

    # -- internal: thread entry point ---------------------------------------

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
