# dghub_sdk 使用指南

社区 Python SDK，为 DGHub 插件提供同步风格的 WebSocket 通信封装。
协议细节请参考 [PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md)。

---

## 安装

从 PyPI 安装（SDK 的唯一官方分发渠道）：

```bash
pip install dghub-sdk
```

> 依赖：Python 3.11+、`websockets`（会自动安装）

> **版本说明**：toolkit 的 Release 版本号是「发布批次号」，并非每次发布都包含
> SDK 变更；SDK 无变更的批次不会向 PyPI 发布新版本，因此 PyPI 上的版本号可能
> 小于最新 Release 号——这是正常现象，PyPI 上的最新版即 SDK 的最新状态。
> GitHub Release 附件不包含 SDK wheel；如确需离线安装包，可从源码自行构建：
>
> ```bash
> cd sdk/python
> pip install -r requirements.txt
> python build_sdk.py          # 产物输出到 dist/
> ```

---

## 快速开始

```python
import dghub_sdk

running = True

def on_stop(reason: str) -> None:
    global running
    running = False

with dghub_sdk.Agent(on_stop=on_stop) as agent:
    agent.wait_ready(timeout=10)   # 等待握手完成
    while running:
        agent.poll()
        # 你的游戏 / 业务逻辑
```

`Agent` 作为上下文管理器使用时，`__enter__` 在后台线程启动 WebSocket
连接（不阻塞）；`__exit__` 断开连接并等待线程退出。

`start()` / `__enter__` 均不等待握手完成。在首次调用 `poll()` 或发送
消息前，应显式调用 `wait_ready()` 确认握手完成：

```python
agent = dghub_sdk.Agent()
agent.start()
agent.wait_ready(timeout=10)
```

需要非阻塞的单次检查时，可用 `is_ready()`：

```python
if agent.is_ready():
    agent.send_status_field("score", score)
```

连接或握手失败会由 `wait_ready()` 直接抛出，
运行期间的后台异常仍可通过 `get_exception()` 读取。
等待后台线程退出使用 `wait_threading_exit()`（`__exit__` 会自动调用）。

`poll()` 从内部消息队列取出已收到的服务端消息，在调用线程上依次触发回调。
默认非阻塞（立即清空队列），传入 `timeout` 参数可阻塞等待。

## 插件根目录与资源文件

`dghub_sdk.plugin_root()` 返回插件根目录，源码与 exe 形态自动一致：

- **exe（Packer 产物）**：exe 所在目录（Packer onedir 布局下 exe 与
  manifest.json、资源同级于插件根）
- **源码（开发调试）**：调用该函数的文件所在目录
- **`DGHUB_PLUGIN_DIR`**：服务端/调试器注入插件根时优先使用（约定绝对路径）

```python
import dghub_sdk

icon = dghub_sdk.plugin_root() / "assets" / "icon.png"   # 读资源统一相对插件根

with dghub_sdk.Agent() as agent:
    ...
```

`Agent.manifest_dir`（公开参数）解析三档：

1. 显式传入——绝对原样；相对以调用方文件目录为基准（raw SDK 用户自写
   插件目录 + manifest.json 时使用）
2. `DGHUB_MANIFEST_DIR` 环境变量——Packer 调试注入（约定绝对路径；
   未来「debug via packer」会注入 `plugin_dir/.dghub-sdk`，用户代码
   零改动）
3. 均未提供——直接用 `plugin_root()` 的插件根（Packer 用户 `Agent()`
   零参数）

手动运行源码且插件根没有 manifest.json 时，握手会报 `FileNotFoundError`
（插件根 manifest 是构建产物；未使用 Packer 的项目需自行维护）。

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

### config 的内容与边界

`config` 是当前插件 ID 下的"配置值快照"，不是 `config_schema` 本身。它通常包含：

- 已经持久化的 `config_schema` 字段值
- 插件通过 `set_config` 写入的自定义字段
- DGHub 管理的公开字段，例如 `target_id`、运行中产生的 `idle_strength`

边界约定：

- `config_schema.default` 不保证自动出现在 `config` 中，尚未保存的字段可能缺失，
  插件应使用 schema 的默认值兜底
- `enabled` 和 `_` 开头的内部字段不会下发
- `target_id` 由 DGHub 管理，插件不能通过 `set_config` 修改
- 握手后收到一次全量 `config`，之后用户修改配置会收到单字段 `config_changed`
- `set_config` 发送后不会回推 `config_changed`，插件应在发送后同步更新自己的本地缓存


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
    name: str | None = None,
    cause: str | None = None,
    pulse_name: str | None = None,
    target_id: str | None = None,
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

### SDK 1.1 事件信息

`send_trigger()` 可通过 `name`、`cause`、`pulse_name` 补充事件的具体内容、
触发原因和实际波形名。`send_event()` 还支持 `from_pct`、`to_pct`、
`delta_pct`，用于让 DGHub 界面完整展示事件前后的强度变化。

### V4 多设备目标

V4 设备信息会以 `DeviceType.V4` 传给 `on_device_info`。通常插件不需要自己
选设备，省略 `target_id` 时 DGHub 会使用插件默认目标；只有一次行为需要明确
发给另一台 V4 设备时，才传消息级目标：

```python
agent.send_pulse(
    "振动-短",
    channel=dghub_sdk.Channel.A,
    target_id="target-1",
)
```

`send_trigger()`、`send_event()`、`send_pulse()`、`send_set_strength()` 和
`send_adjust_strength()` 都支持可选的 `target_id`。省略时不会在 JSON 中发送
该字段，因此 V2/V3 和旧调用方式保持不变。`target_id` 仍由 DGHub 管理，
不要用 `send_set_config()` 修改它。

---

## 状态上报

SDK 提供多个便捷方法上报插件状态：

### send_startup_check —— 启动检查

内部维护 steps 状态，每次调用更新或新增对应 step 并自动发送：

```python
from dghub_sdk import CheckState

# 初始化时批量设置 steps（不发送）
agent.send_startup_check("plugin", "插件连接", CheckState.IDLE, dont_send=True)
agent.send_startup_check("game", "游戏连接", CheckState.IDLE, dont_send=True)
# 最后一个调用触发发送
agent.send_startup_check("device", "设备连接", CheckState.IDLE,
                         display_status="初始化中")

# 之后逐步更新，每次自动发送
agent.send_startup_check("plugin", "插件连接", CheckState.OK, detail="已连接 DGHub")
agent.send_startup_check("game", "游戏连接", CheckState.OK, detail="已连接",
                         display_status="运行中")
```

面板标题默认为 `"Startup Check"`，可通过 `set_startup_check_title()` 修改。

`state` 可选值定义在 `CheckState` 枚举中：`idle` / `pending` / `ok` / `warn` / `fail`。

### send_display_status —— 显示状态

```python
agent.send_display_status("运行中")
```

### send_status_field —— 单字段上报

```python
agent.send_status_field("tick", 42)
```

### send_status —— 底层 API

以上方法底层均调用 `send_status(fields: dict)`，可直接使用：

```python
agent.send_status({"custom_field": 42})
```

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
set DGHUB_PORT=8000
set DGHUB_TOKEN=<从 GET /api/plugins/_session_token 获取>
python main.py
```

或在代码中临时 patch：

```python
import os
os.environ["DGHUB_HOST"] = "127.0.0.1"
os.environ["DGHUB_PORT"] = "8000"
os.environ["DGHUB_TOKEN"] = "your-token-here"
```

Token 可从 DGHub 运行时通过 `GET http://127.0.0.1:8000/api/plugins/_session_token` 获取。

---

## 更多

- 完整协议字段定义：[PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md)
- API 签名与参数说明：参见源码中的 Google-style docstrings
