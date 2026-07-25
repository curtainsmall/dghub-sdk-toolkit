# dghub_sdk 使用指南

社区 Python SDK，为 DGHub 插件提供同步风格的 WebSocket 通信封装。
协议细节请参考 [PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md)。

---

## 安装

从 [Releases](https://github.com/curtainsmall/dghub-sdk-toolkit/releases) 下载 `.whl` 文件，然后：

```bash
pip install dghub_sdk-x.x.x-py3-none-any.whl
```

> 依赖：Python 3.11+、`websockets`（会随 whl 自动安装）

---

## 快速开始

```python
import dghub_sdk

running = True

def on_stop(reason: str) -> None:
    global running
    running = False

with dghub_sdk.Agent(on_stop=on_stop) as agent:
    while running:
        agent.poll()
        # 你的游戏 / 业务逻辑
```

`Agent` 作为上下文管理器使用时，`__enter__` 自动在后台线程建立 WebSocket
连接并完成握手；`__exit__` 断开连接并等待线程退出。

`poll()` 从内部消息队列取出已收到的服务端消息，在调用线程上依次触发回调。
默认非阻塞（立即清空队列），传入 `timeout` 参数可阻塞等待。

---

## 配置监听

DGHub 通过两个时机推送配置：

| 回调 | 触发时机 | 签名 |
|------|----------|------|
| `on_config` | 握手完成后，推送全量配置 | `(config: dict[str, Any]) -> None` |
| `on_config_changed` | 用户在前端修改单个字段 | `(key: str, value: Any) -> None` |

典型用法：

```python
from typing import Any

config: dict[str, Any] = {}

def on_config(cfg: dict[str, Any]) -> None:
    """握手后收到全量配置，初始化本地状态。"""
    config.update(cfg)

def on_config_changed(key: str, value: Any) -> None:
    """用户修改了一个配置项，增量更新。"""
    config[key] = value

with dghub_sdk.Agent(on_config=on_config,
                     on_config_changed=on_config_changed) as agent:
    ...
```


---

## 强度触发

`send_trigger` 是推荐的核心方法——一条调用同时控制强度、波形、通道：

```python
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
) -> None: ...
```

### Rollback（临时）

强度临时偏移 baseline，duration 结束后自动回正：

```python
agent.send_trigger(
    action=dghub_sdk.Action.BOTH,
    delta_pct=50,
    strength_mode=dghub_sdk.StrengthMode.ROLLBACK,
    duration_s=1.5,
    preset="CS2-受伤",
    label="受击",
)
```

### Permanent（永久）

永久修改 baseline：

```python
agent.send_trigger(
    action=dghub_sdk.Action.STRENGTH,
    delta_pct=10,
    strength_mode=dghub_sdk.StrengthMode.PERMANENT,
)
```

### 仅波形

不改强度，只播放一段触感反馈：

```python
agent.send_trigger(
    action=dghub_sdk.Action.WAVEFORM,
    preset="振动-短",
    duration_s=0.5,
)
```

---

## 状态上报

通过 `send_status` 向主程序报告插件运行状态，驱动前端状态卡片和启动检查面板：

```python
def send_status(self, fields: dict[str, Any]) -> None: ...
```

示例——启动检查：

```python
agent.send_status({
    "display_status": "等待游戏连接",
    "startup_check": {
        "title": "我的插件",
        "steps": [
            {"key": "game", "title": "游戏连接",
             "state": "pending", "detail": "未检测到游戏进程"},
        ],
    },
})
```

`state` 可选值定义在 `CheckState` 枚举中：`idle` / `pending` / `ok` / `warn` / `fail`。

---

## 错误处理

后台线程中的异常不会直接抛出，而是被收集到内部队列。
在主循环中调用 `get_exception()` 检查：

```python
while running:
    agent.poll()

    while exc := agent.get_exception():
        print(f"[错误] {exc}")
        # 根据严重程度决定是否退出
```

---

## 手动接入（调试）

正常情况下 DGHub 会自动 spawn 你的插件进程并设置环境变量。
调试时可以手动启动插件，只需提前设置环境变量：

```bash
set DGHUB_HOST=127.0.0.1
set DGHUB_PORT=27020
set DGHUB_TOKEN=<从 GET /api/plugins/_session_token 获取>
python main.py
```

或在代码中临时 patch：

```python
import os
os.environ["DGHUB_HOST"] = "127.0.0.1"
os.environ["DGHUB_PORT"] = "27020"
os.environ["DGHUB_TOKEN"] = "your-token-here"
```

Token 可从 DGHub 运行时通过 `GET http://127.0.0.1:27020/api/plugins/_session_token` 获取。

---

## 更多

- 完整协议字段定义：[PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md)
- API 签名与参数说明：参见源码中的 Google-style docstrings
