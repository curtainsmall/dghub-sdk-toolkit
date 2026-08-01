# DGHub SDK Packer 使用指南

图形化桌面工具，帮助开发者配置插件信息、打包并分发 DGHub 插件（产物
`manifest.json` 构建时自动生成）。纯 GUI 工具（无 CLI）：配置与构建均在
界面内完成；CI / 脚本化场景请直接使用 [DGHub SDK](../sdk/dghub_sdk.py)
编程。以插件目录下的 `.dghub-sdk/` 为项目数据源（类比 `.git/`，是
「Packer 项目」的标志）。

---

## 下载与安装

从 [Releases](https://github.com/curtainsmall/dghub-sdk-toolkit/releases) 下载
`dghub-sdk-packer-setup.exe`，双击安装（每用户安装，无需管理员）。安装后
开始菜单「DGHub SDK Packer」启动 GUI。

如需从源码运行（需要 [uv](https://docs.astral.sh/uv/)）：

```bash
uv sync --project packer
uv run --project packer python packer/src/gui/main.py
```

---

## 概念：两阶段构建

Packer 把「源码项目 → DGHub 插件包」拆成两阶段：

```
阶段 1：pre-build 预构建（可选，显式单选）
   ├─ (None)          不执行任何构建步骤，直接收集打包内容
   ├─ Python          按依赖清单自动下载依赖 → PyInstaller 打包为自包含 exe（onedir）
   └─ 自定义命令       构建前执行用户命令（如编译），产物由打包内容声明
      │
      ▼
阶段 2：统一构建步骤（对所有预构建一致）
   收集打包内容 + 预构建产物 → 生成 manifest.json → 组装 zip / 文件夹
```

插件包结构（通用）：`manifest.json + 入口产物 + 其它资源（保留相对路径）`。
Python 预构建的产物是 onedir 树（`<名>.exe` + `_internal/`），收集时整树进入包。

---

## GUI 使用

### 工作流概览

```
选择插件目录 → （预构建页）选择/配置预构建 → （构建页）打包内容 → 构建
```

1. **打开插件目录** — 顶部栏选择插件目录（任意文件夹均可；Packer 在其中创建/读取 `.dghub-sdk/` 存放插件配置，首次选择即初始化新项目）
2. **预构建页** — 下拉单选预构建（无 / Python / 自定义命令），并按所选预构建填写设置（见下）
3. **信息页** — 填写插件元信息与配置 schema，产物 `manifest.json` 构建时自动生成
4. **构建页** — 项目根、入口文件、打包内容（文件/目录/规则，可标记入口）与发布选项
5. **构建** — 导出 `.zip`（分发）或文件夹（调试）

### 预构建

预构建页显式选择 pre-build 预构建（单选下拉），选中后显示对应设置字段：

- **(None)** — 不执行 pre-build，构建页的打包内容直接收集（纯收集模式）
- **Python (uv + PyInstaller)** — 依赖清单必填（`pyproject.toml` / `setup.py` / `setup.cfg` / `requirements*.txt`，均为 uv 可识别格式）；可选「包含 dghub-sdk」；清单格式受支持时绿色 `✓` 标注，不受支持浅红警示；旁有 PyInstaller 可用性标注（未检测到提示 `pip install pyinstaller`，Packer 不自动安装）
- **自定义命令** — 预构建命令必填（如 `dotnet build -c Release`），构建时先在执行目录执行（默认项目根），非零返回码视为构建失败；执行目录行仅在填写命令后可用

「从预构建填充构建内容」按钮（构建页）串联探测与推导：Python 预构建会自动
探测 `pyproject.toml`（建议清单与 `[tool.dghub].entry` 入口）并推导打包内容
中的入口条目（`<插件名>.exe`）；只填空，不覆盖已有设置。

### 构建

构建页配置打包内容与发布选项：

- **项目根** — 收集根（入口、打包内容条目均相对它解析）；未设置时回退插件目录
- **入口文件** — 阶段 1 输入：Python 预构建时为 `.py` 源码入口；无预构建/自定义命令时为产物路径；`[tool.dghub].entry` 约定可由「从预构建填充」自动应用
- **打包内容** — 统一文件选择列表，支持三种条目：
  - 文件（`添加` 打开混合选择对话框，文件与文件夹均可多选；选文件夹 = 目录条目，递归收集）
  - 目录（保留相对子目录结构发布）
  - 规则（`添加规则`，glob 如 `dist/**`，构建时求值）
  - 入口由「设为入口」标记（列表显示绿色「入口」徽标；恰好一个，缺失/重复构建校验报错）
- **No Zip** — 复选框：不勾 = `.zip` 包（默认，分发）；勾选 = 输出文件夹（本地调试）
- **输出目录** — 顶部栏选择（空 = 插件目录/output）
- **输出文件预览** — 实时树（打包内容 + Python 预构建产物 = exe + `_internal/`）

依赖由项目自身的清单文件管理，Packer 只读清单并安装到中间目录（`.deps/`），
**不修改项目源文件、不修改项目外文件**（只写 `.dghub-sdk/` 与输出目录）。
Python 预构建打包的 exe 完全自包含：依赖打进 `_internal/`，**DGHub 运行环境
对 exe 不可见**（websockets 等基础依赖不免费，需在清单中声明）。

### 构建执行与取消

- 点击底部「**开始构建**」启动；构建在后台运行，全过程锁定目录选择与各页编辑，避免中途改动导致状态不一致
- 校验一次性检测所有必填项（信息页 id / name / version、入口文件、预构建必要字段、打包内容入口条目、输出目录），错误一次全部高亮；修正任一字段即刻恢复其边框，该页错误全部清除后标题高亮与「构建失败」状态一并消除
- 构建期间「开始构建」按钮变为「**取消构建**」：点击弹出二次确认，确认后立即终止正在运行的命令（pre-build / 依赖安装 / 打包，含其子进程树），并清理输出目录内已产生的中间产物（**不触碰用户源目录中的 pre-build 产物**）
- 关闭窗口时若构建仍在进行，会先终止子进程再退出，不残留 uv / PyInstaller / pre-build 进程

### 设置

应用设置与关于页：

- **外观模式** — system / light / dark 主题切换
- **PyPI 镜像源** — 打包依赖（uv 下载）时使用的下载源（默认官方 pypi.org，预置清华 / 阿里云 / 中科大镜像）。网络无法访问官方源时切换为国内镜像即可；选择实时保存，全局生效（跨项目）。选「官方」时不注入任何配置，uv 自身的环境变量与配置文件照常生效
- 应用版本信息、相关链接与开源协议（AGPLv3）

### 日志

构建全过程输出集中显示：校验、pre-build、依赖安装、PyInstaller、打包逐步记录；校验失败与构建错误在此给出具体原因；旧版配置迁移等提示也记录于此。

- 分级着色：**错误**（红）/ **警告**（橙）/ **成功**（绿，仅最终产物 zip / 文件夹）三类着色，其余为普通信息（默认色）
- 外部工具（uv / PyInstaller 等）的原始输出以 `─── 来源 ───` 分隔块成段展示，并标注退出码
- 日志不自动清空：每次构建前插入 `━━━ 构建 时间 ━━━` 分隔行、历史累积，便于回看与对比；右上角「清空」按钮可手动清空

---

## 项目配置（.dghub-sdk/project.json）

配置由 GUI 管理，无需手写；格式为 format_version 2（顶层平铺 + builder 节）：

```json
{
  "format_version": 2,
  "producer": "python",
  "source_dir": "",
  "entry": "src/main.py",
  "pre_build": "",
  "exec_dir": "",
  "manifest": "pyproject.toml",
  "include_sdk": true,
  "builder": {
    "files": [
      { "path": "my-plugin.exe", "tags": ["entry"] },
      { "dir": "assets" },
      { "pattern": "dist/**" }
    ],
    "no_zip": false,
    "output_dir": ""
  }
}
```

旧格式（format_version 1）打开时自动迁移（字段归位、预构建推断、`extra_files`
去 dest 入 `files`、`target` 映射 `no_zip`），日志提示检查设置。

---

## 从源码构建安装器

将 Packer 打包为 Windows 安装器（一步完成「源码 → onedir → 安装器」）：

```bash
uv sync --project packer
uv run --project packer python packer/build.py            # 可选 --version X.Y.Z
```

- 单 GUI exe（onedir：`dgpacker-gui.exe` + 共享 `_internal/`，无每次启动解压 → 启动更快）
- 产物：`packer/installer/dghub-sdk-packer-setup.exe`（onedir 中间物在 `packer/bin/dghub-sdk-packer/`）
- **前置**：本机需装 [Inno Setup 6](https://jrsoftware.org/isinfo.php)（`ISCC` 在 PATH 或默认安装目录）；若 `[Languages]` 用到简体中文，需 `ChineseSimplified.isl` 在 Inno 的 `Languages\` 目录

> 依赖（含 PyInstaller）由 `packer/pyproject.toml` 声明，`uv sync` 会自动安装；Inno Setup 需单独安装。
