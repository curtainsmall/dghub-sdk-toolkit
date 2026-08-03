import asyncio
import json
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
from websockets.exceptions import ConnectionClosed
from websockets.sync.server import serve

import dghub_sdk
from dghub_sdk import Agent, plugin_root


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


# ---------------------------------------------------------------------------
# plugin_root()：无查找、全直接来源；默认分支缓存受 env/frozen 影响，
# 每个用例前后 cache_clear 保证隔离
# ---------------------------------------------------------------------------


def test_plugin_root_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """源码形态：无参返回调用者文件目录（现状语义）。"""
    monkeypatch.delenv("DGHUB_PLUGIN_DIR", raising=False)
    plugin_root.cache_clear()
    try:
        assert plugin_root() == Path(__file__).resolve().parent
    finally:
        plugin_root.cache_clear()


def test_plugin_root_frozen(tmp_path: Path,
                            monkeypatch: pytest.MonkeyPatch) -> None:
    """frozen 模拟：返回 exe 目录（修复 _MEIPASS 陷阱）。"""
    monkeypatch.delenv("DGHUB_PLUGIN_DIR", raising=False)
    fake_exe = tmp_path / "plugin" / "my-plugin.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    plugin_root.cache_clear()
    try:
        assert plugin_root() == fake_exe.parent
    finally:
        plugin_root.cache_clear()
        monkeypatch.setattr(sys, "frozen", False, raising=False)


def test_plugin_root_cached() -> None:
    """进程内缓存：多次无参调用返回同一对象。"""
    plugin_root.cache_clear()
    try:
        assert plugin_root() is plugin_root()
    finally:
        plugin_root.cache_clear()


def test_plugin_root_explicit_param(tmp_path: Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """显式参数原样返回（不 resolve 不校验）；同参缓存同一对象；与无参互不干扰。"""
    p = tmp_path / "some" / "dir"
    assert plugin_root(p) == p
    assert plugin_root(p) is plugin_root(p)
    # 无参默认分支不受显式调用影响
    monkeypatch.delenv("DGHUB_PLUGIN_DIR", raising=False)
    plugin_root.cache_clear()
    try:
        assert plugin_root() == Path(__file__).resolve().parent
    finally:
        plugin_root.cache_clear()


def test_plugin_root_env_plugin_dir(tmp_path: Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """DGHUB_PLUGIN_DIR 优先于形态起点；显式参数优先于 env。"""
    env_dir = tmp_path / "env-root"
    monkeypatch.setenv("DGHUB_PLUGIN_DIR", str(env_dir))
    plugin_root.cache_clear()
    try:
        assert plugin_root() == env_dir.resolve()
        # 显式参数优先于 env
        assert plugin_root(tmp_path / "x") == tmp_path / "x"
    finally:
        plugin_root.cache_clear()


# ---------------------------------------------------------------------------
# Agent.manifest_dir 三档解析：显式 → DGHUB_MANIFEST_DIR → plugin_root()
# ---------------------------------------------------------------------------


def test_agent_env_manifest_dir(agent_environment: Path,
                                monkeypatch: pytest.MonkeyPatch) -> None:
    """DGHUB_MANIFEST_DIR：_manifest_dir 为该值（resolve）；显式参数优先于 env。"""
    env_manifest = agent_environment.parent / "env-manifest"
    monkeypatch.setenv("DGHUB_MANIFEST_DIR", str(env_manifest))
    agent = Agent(max_retries=0)
    assert agent._manifest_dir == env_manifest.resolve()
    # 显式参数优先于 env
    agent2 = Agent(manifest_dir=agent_environment, max_retries=0)
    assert agent2._manifest_dir == agent_environment


def test_agent_default_plugin_root(agent_environment: Path,
                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """无显式无 env：_manifest_dir = plugin_root()（直接复用）。

    注：源码形态下 Agent.__init__ 内调用 plugin_root() 时，caller 帧为
    agent.py（__init__ 帧），故默认值为 agent.py 所在目录——"直接用
    plugin_root()"简单方案的已知边界（frozen/env 场景不受影响）。
    """
    monkeypatch.delenv("DGHUB_MANIFEST_DIR", raising=False)
    monkeypatch.delenv("DGHUB_PLUGIN_DIR", raising=False)
    plugin_root.cache_clear()
    try:
        agent = Agent(max_retries=0)
        assert agent._manifest_dir == Path(dghub_sdk.__file__).resolve().parent
    finally:
        plugin_root.cache_clear()
