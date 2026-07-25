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

```python
import dghub_sdk

with dghub_sdk.Agent() as agent:
    agent.on_config_changed = lambda key, value: print(key, value)
    while True:
        agent.poll()
```

详细用法参见 [SDK 使用指南](docs/sdk.md)。

## Plugin Packer

位于 `packer/`，图形化桌面应用，帮助开发者打包和分发 DGHub 插件。

- Manifest 编辑器 — 可视化编辑 `manifest.json`
- 依赖打包 — 将第三方 Python 包打包到 `vendor/`
- 发布 — 导出 `.zip` 或构建为独立 `.exe`

### 下载

从 [Releases](https://github.com/curtainsmall/dghub-sdk-toolkit/releases) 下载 `DGHubPluginPacker.exe` 直接运行。

### 从源码运行

```bash
pip install -r packer/requirements.txt

# 运行
python -m packer.src.main

# 打包为单文件 exe
python packer/build_exe.py
```

## Demo

`demo/tetris/` — 俄罗斯方块示例插件，演示 SDK 集成与强度触发。

## License

AGPLv3 · 适用于 DGHub SDK v1

---

**See Also:** [插件开发协议规范](docs/PLUGIN_DEVELOPMENT.md) · [Plugin Packer 指南](docs/packer.md)
