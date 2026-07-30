# DGHub SDK Toolkit

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![License](https://img.shields.io/badge/License-AGPLv3-green)

[DGHub](http://dghub.top/) 插件开发工具集，包含 Python SDK 和图形化打包工具。

## SDK

位于 `sdk/python/`，提供插件与 DGHub 主程序之间的 WebSocket 通信封装。

- 自动连接与会话管理
- 配置同步
- 强度控制
- 设备状态监听

### 安装（PyPI 为官方分发渠道）：

```bash
pip install dghub-sdk
```

### 使用
```python
import dghub_sdk

with dghub_sdk.Agent() as agent:
    agent.on_config_changed = lambda key, value: print(key, value)
    agent.wait_ready(timeout=10)   # 等待握手完成后再 poll
    while True:
        agent.poll()
```

详细用法参见 [SDK 使用指南](docs/sdk.md)。

## Packer

位于 `packer/`，图形化桌面应用，帮助开发者打包和分发 DGHub 插件。

- 多构建系统 — `Python - uv`（从源码构建）或 `(无构建系统)`（直接打包已有产物）
- 插件信息编辑 — 可视化填写元信息与 `config_schema`，产物 `manifest.json` 构建时自动生成
- 依赖管理 — 依赖由项目自身清单（`pyproject.toml`）声明，构建时安装到 `vendor/`
- 发布 — 导出 `.zip` 或文件夹，Python 项目可选构建为独立 `.exe`

### 下载

从 [Releases](https://github.com/curtainsmall/dghub-sdk-toolkit/releases) 下载 `DGHubPluginPacker.exe` 直接运行。

### 从源码运行

```bash
# 安装依赖（需要 uv）
uv sync --project packer

# 运行
uv run --project packer python -m packer.src.main

# 打包为单文件 exe
uv run --project packer python packer/build_exe.py
```

详细用法参见 [Plugin Packer 使用指南](docs/packer.md)。

## Demo

`demo/tetris/` — 俄罗斯方块示例插件，演示 SDK 集成与强度触发。

## License

AGPLv3 · 适用于 DGHub SDK v1

---

**另见：**[插件开发协议规范](docs/PLUGIN_DEVELOPMENT.md)
