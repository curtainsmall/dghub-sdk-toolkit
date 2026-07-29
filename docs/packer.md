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
选择插件目录 → 选择构建体系 → 编辑 Manifest → 配置发布内容 → 构建
```

1. **打开插件目录** — 选择包含 `manifest.json` 的文件夹（或新建项目）
2. **选择构建体系** — 顶部栏下拉框选择（每种语言钦定一个体系，文案为「语言 - 构建体系」）：
   - `Python - uv` — Python 项目，依赖清单为 `pyproject.toml`（也可选 `requirements.txt`，uv 同样能消费）
   - `(无构建系统)` — 不使用任何构建器，直接打包已构建的原始文件
3. **编辑 Manifest** — 在信息标签页填写插件元信息和配置 schema
4. **配置发布内容** — 在发布标签页指定目录、入口、附加文件、发布目标
5. **构建** — 导出 `.zip` / 文件夹，Python 体系可选构建为独立 `.exe`

---

## 各标签页简述

### 信息

可视化编辑 `manifest.json`：

- 基础字段（id / name / version / author / entry 等）
- `config_schema` 编辑器 — 拖拽式添加 section 与 field，支持所有字段类型
- `capabilities` 开关
- 实时校验：ID 格式、必填项、语义化版本

### 发布

打包内容、构建选项与发布目标，内容随构建体系切换。

依赖由项目自身的清单文件管理，Packer 只读清单并安装到 `vendor/`，**不修改项目源文件、不修改项目外文件**（只写 `.dghub-sdk/` 与输出目录）。

**Python - uv**（从 Python 源码构建插件）：

- 依赖清单 — 在视图内选择清单文件（`pyproject.toml`，也可选 requirements 格式文件）；**项目根 = 清单所在目录**，入口与依赖安装均以此为基准；未选择时跳过依赖打包（无第三方依赖属正常情形），项目根 = 插件目录
- 依赖来源面板 — 显示选定的清单与工具可用性；清单内容不做逐包过滤，dghub-sdk 由「包含 dghub-sdk」选项单独注入
- 入口文件 — 必须为 `.py` 文件，相对项目根；可在 pyproject.toml 中声明 `[tool.dghub]` 段的 `entry = "src/main.py"`，选择清单时自动填充入口（仍可修改；Packer 只读不写该文件）
- 构建选项 — 可选构建为独立 exe（需要 PyInstaller，复选框旁有工具依赖标注，未检测到时变红提示）、可选包含 dghub-sdk；另有 uv 可用性标注（未检测到提示 `pip install uv`，Packer 不自动安装）

**(无构建系统)**（不使用任何构建器，直接打包原始文件）：

- 工作目录 — 在视图内选择，是原始文件的选取根，也是 pre-build 命令的执行目录（如 `bin/Release/`）
- 构建命令 (pre-build) — 可选；填写后构建时先在工作目录执行（如 `dotnet build -c Release`），非零返回码视为构建失败
- 入口文件 — 可编辑输入或用选择器指定，可为任意文件（`.exe` / `.js` / `.bat` 等）；允许填写 pre-build 将生成的文件，存在性在 pre-build 执行后才校验
- 附加文件 — 支持两种条目：精确文件（多选添加）与 glob 规则（如 `*.dll`、`dist/**`，构建时在 pre-build 后求值）；每条可指定放入根目录（如 `.dll`）或 `vendor/`
- 不执行任何语言特定构建，产物为 manifest + 清单文件的打包

各体系的目录与配置按体系独立记忆，切换互不影响；均支持发布为 `.zip`（分发）或文件夹（本地调试），底部预览实时显示输出结构（含规则当前匹配结果）。

### 设置

应用设置与关于页：

- **外观模式** — system / light / dark 主题切换
- **PyPI 镜像源** — 打包依赖到 `vendor/` 时使用的下载源（默认官方
  pypi.org，预置清华 / 阿里云 / 中科大镜像）。网络无法访问官方源
  （如超时、TLS 握手失败）时切换为国内镜像即可；选择实时保存，
  全局生效（跨项目）。选「官方」时不注入任何配置，uv 自身的
  环境变量与配置文件照常生效
- 应用版本信息与相关链接

---

## 从源码构建 EXE

将 Plugin Packer 自身打包为独立可执行文件：

```bash
uv sync --project packer
uv run --project packer python packer/build_exe.py
```

产物输出到 `packer/bin/DGHubPluginPacker.exe`。

> 依赖（含 PyInstaller）由 `packer/pyproject.toml` 声明，`uv sync` 会自动安装
