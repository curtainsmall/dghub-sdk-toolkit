import asyncio
import json
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
from websockets.exceptions import ConnectionClosed
from websockets.sync.server import serve

from dghub_sdk import Agent


@contextmanager
def _handshake_server(*, accepted: bool = True, delay: float = 0.0):
    def handler(websocket) -> None:
        websocket.recv()
        if delay:
            time.sleep(delay)
        websocket.send(json.dumps({
            "op": "hello_ack",
            "accepted": accepted,
            "reason": None if accepted else "rejected for test",
            "sdk_version": "1.1.0",
        }))
        try:
            for _ in websocket:
                pass
        except ConnectionClosed:
            pass

    server = serve(handler, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.socket.getsockname()[1]
    finally:
        server.shutdown()
        thread.join(timeout=2)


@pytest.fixture
def agent_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "manifest.json").write_text(json.dumps({
        "id": "test_plugin",
        "name": "Test Plugin",
        "version": "0.1.0",
        "sdk": "1",
    }), encoding="utf-8")
    monkeypatch.setenv("DGHUB_HOST", "127.0.0.1")
    monkeypatch.setenv("DGHUB_TOKEN", "test-token")
    return tmp_path


def test_context_manager_starts_without_blocking(
    agent_environment: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _handshake_server(delay=0.1) as port:
        monkeypatch.setenv("DGHUB_PORT", str(port))
        agent = Agent(manifest_dir=agent_environment, max_retries=0)

        entered = agent.__enter__()
        try:
            assert entered is agent
            # __enter__ 不等待握手，需手动调用 wait_ready
            agent.wait_ready(timeout=2)
            assert agent.connected is True
            assert agent.is_ready() is True
        finally:
            agent.stop()
            agent.wait_threading_exit(timeout=2)

        assert agent.connected is False
        assert agent.is_ready() is False
        assert agent._thread is not None
        assert agent._thread.is_alive() is False


def test_wait_ready_surfaces_handshake_rejection(
    agent_environment: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _handshake_server(accepted=False) as port:
        monkeypatch.setenv("DGHUB_PORT", str(port))
        agent = Agent(manifest_dir=agent_environment, max_retries=0)

        with pytest.raises(ConnectionError, match="rejected for test"):
            with agent:
                agent.wait_ready(timeout=2)


def test_manual_start_can_wait_ready(
    agent_environment: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _handshake_server(delay=0.2) as port:
        monkeypatch.setenv("DGHUB_PORT", str(port))
        agent = Agent(manifest_dir=agent_environment, max_retries=0)
        started_at = time.monotonic()

        agent.start()
        start_elapsed = time.monotonic() - started_at
        try:
            assert agent.is_ready() is False
            agent.wait_ready(timeout=2)
            assert agent.connected is True
            assert agent.is_ready() is True
            assert start_elapsed < 0.1
        finally:
            agent.stop()
            agent.wait_threading_exit(timeout=2)


def test_background_send_failures_are_reported(
    agent_environment: Path,
) -> None:
    class FailingWebSocket:
        async def send(self, raw: str) -> None:
            raise OSError(f"send failed: {raw}")

    agent = Agent(manifest_dir=agent_environment)
    loop = asyncio.new_event_loop()
    loop_ready = threading.Event()

    def run_loop() -> None:
        asyncio.set_event_loop(loop)
        loop_ready.set()
        loop.run_forever()

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    loop_ready.wait(timeout=1)
    agent._loop = loop
    agent._ws = FailingWebSocket()

    try:
        agent.send("test-message")
        deadline = time.monotonic() + 1
        error = None
        while error is None and time.monotonic() < deadline:
            error = agent.get_exception()
            time.sleep(0.01)

        assert isinstance(error, OSError)
        assert str(error) == "send failed: test-message"
    finally:
        agent._ws = None
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=1)
        loop.close()
