# Plugin Packer 使用指南

图形化桌面工具，帮助开发者编辑 manifest、管理依赖、打包并分发 DGHub 插件。

---

## 下载与运行

从 [Releases](https://github.com/curtainsmall/dghub-sdk-toolkit/releases) 下载
`DGHubPluginPacker.exe`，双击即可运行，无需安装。

如需从源码运行（需要 [uv](https://docs.astral.sh/uv/)）：

```bash
uv sync --project packer
uv run --project packer python -m packer.src.main
```

---

## 工作流概览

```
选择插件目录 → 编辑 Manifest → 打包依赖 → 导出发布
```

1. **打开插件目录** — 选择包含 `manifest.json` 的文件夹（或新建项目）
2. **编辑 Manifest** — 在 Manifest 标签页填写插件元信息和配置 schema
3. **打包依赖** — 在 Dependency 标签页将第三方 Python 包收集到 `vendor/`
4. **导出发布** — 在 Distribute 标签页导出 `.zip` 或构建为独立 `.exe`

---

## 各标签页简述

### Manifest

可视化编辑 `manifest.json`：

- 基础字段（id / name / version / author / entry 等）
- `config_schema` 编辑器 — 拖拽式添加 section 与 field，支持所有字段类型
- `capabilities` 开关
- 实时校验：ID 格式、必填项、语义化版本

### Dependency

管理插件的第三方 Python 依赖：

- 输入包名 → 自动下载并解包到 `vendor/`
- 显示已打包的依赖列表
- 支持删除不再需要的依赖

### Distribute

插件打包与发布：

- **导出 ZIP** — 将插件目录打包为标准 `.zip`，用户可直接在 DGHub 中导入
- **构建 EXE** — 调用 PyInstaller 将 Python 插件编译为独立可执行文件

### Settings

应用设置：

- Python 解释器路径配置（用于依赖打包和 EXE 构建）
- PyInstaller 参数自定义

---

## 从源码构建 EXE

将 Plugin Packer 自身打包为独立可执行文件：

```bash
uv sync --project packer
uv run --project packer python packer/build_exe.py
```

产物输出到 `packer/bin/DGHubPluginPacker.exe`。

> 依赖（含 PyInstaller）由 `packer/pyproject.toml` 声明，`uv sync` 会自动安装
