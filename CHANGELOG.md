# Changelog

本项目的所有重要变更记录在此文件。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。
版本号为 toolkit 发布批次号，Packer 与 SDK 统一使用；SDK 仅在自身有变更
的批次发布至 PyPI（版本跳号为预期行为）。

## [0.3.0] - 2026-07-30

### 新增

- **Packer**：构建选项「包含 dghub-sdk」在非 exe 模式下也生效——将本地
  dghub-sdk 复制进 `vendor/`；exe 与非 exe 模式均遵循「清单优先」，若依赖
  清单已声明 dghub-sdk 则以清单版为准并跳过本地注入（避免版本撞车）
- **Packer**：uv 依赖清单支持 `pyproject.toml` / `setup.py` / `setup.cfg` /
  `requirements*.txt`，文件选择对话框按这些格式过滤；依赖来源面板三态显示
  （绿色已选 / 黄色未选 / 浅红未知格式），未知格式在构建校验时拦截
- **Packer**：构建日志分级着色——错误（红）/ 警告（橙）/ 成功（绿）三色，
  其余为默认色；外部工具（uv / PyInstaller 等）输出以「来源分隔块」成段展示；
  日志页新增「清空」按钮
- **Packer**：支持**取消构建**——构建期间「开始构建」按钮变为「取消构建」，
  二次确认后立即终止正在运行的命令（pre-build / 依赖安装 / 打包，含子进程树，
  Windows 用 `taskkill /T`）；取消后仅清理输出目录内的中间产物；关闭窗口时若
  构建进行中会先终止子进程再退出，不残留进程

### 变更

- **Packer**：「发布」标签页更名为「构建」（内容为构建配置，与底部
  「构建」按钮呼应；"发布目标"选项名不变）；底部按钮文案改为
  「开始构建 / 正在构建」
- **Packer**：构建系统说明文案移至顶部栏选择器右侧（原在构建页内）
- **发布流程**：GitHub Release 标题精简为版本号（如 `v0.3.0`）；正文不再
  附加自动生成的「What's Changed」（其仅统计 PR，对本项目直推发布流无效），
  内容完全由本文件对应版本段落提供
- **Packer**：构建不再自动清空日志——改为保留历史，每次构建前插入
  `━━━ 构建 时间 ━━━` 分隔行；仅最终产物（zip / 文件夹）标记为成功绿，
  校验通过、依赖打包、exe 构建等中间步骤为普通信息
- **Packer**：目录显示区移除路径悬停提示（tooltip），超长路径仍截断显示
- **Packer**：构建期间锁定构建系统选择器、目录选择与信息/构建页编辑，
  避免中途改动导致状态不一致
- **Packer（内部）**：日志改为结构化分级（调用点显式声明级别，不再解析文本
  前缀）；移除遗留死代码 `vendor_packer`（系统 Python 定位函数并入 `exe_builder`）

### 修复

- Packer exe 构建入口未同步构建页配置的 entry（`src/` 布局下曾误用插件根
  的 `main.py` 导致构建失败）
- Packer 构建页入口文件输入框与上下行左边界未对齐（标签列缺 5px 间距）
- Packer 错误高亮生命周期：修正字段错误的输入框在清除时未恢复默认灰边（曾被
  抹成无边框）；修正字段修正后 tab 标题高亮与「构建失败」状态标签不消除的问题；
  校验改为一次点击检测所有必填项（原先逐个暴露、修一个冒一个）
- Packer 默认输出目录标签在构建开始时误从灰字变为正常深色，现按自动/手动状态
  保持正确颜色
- 修正 Packer 文档中过时的信息：manifest 口径统一为**构建时自动生成**
  （移除"编辑 manifest"表述）；插件目录不再要求预先存在 `manifest.json`
  （任意文件夹首次选择即初始化）；信息页字段列表与实际一致（entry 移至
  构建页按构建系统配置）；补充日志页说明；README 功能列表同步
- Packer 部分警告（清单已含 dghub-sdk、未选清单跳过依赖、glob 规则无匹配）
  此前未着色或被误标为「提示」，现统一归为警告；移除 exe 构建后过时的
  「手动修改 manifest entry」提示（产物 manifest 已自动写入 entry）

## [0.2.1] - 2026-07-29

### 修复

- 修正 README 中过时的信息：SDK 快速示例补充 `wait_ready()` 调用
  （0.2.0 起 `with Agent()` 不再自动等待握手）；Packer 功能列表更新为
  构建系统驱动模型（多构建系统、依赖由项目清单声明），移除已废弃的
  「依赖打包」旧描述；补充 SDK 的 PyPI 安装说明

## [0.2.0] - 2026-07-29

### ⚠️ 破坏性变更

- **SDK**：`Agent.wait()` 重命名为 `wait_threading_exit()`。直接调用
  `wait()` 会触发 `AttributeError`，请改名调用；使用 `with` 语句的插件
  不受影响（`__exit__` 内部已适配）
- **Packer**：发布工作流重构为「构建系统驱动」——顶部栏选择构建系统
  （`Python - uv` / `(无构建系统)`），Dependency 标签页移除，依赖改由
  项目自身清单（pyproject.toml / requirements.txt）管理；
  `.dghub-sdk/project.json` 结构升级为按系统命名空间存储

### 新增

- **SDK**：SDK 1.1 / V4 设备兼容——`DeviceType.V4`；`trigger` / `event` /
  `pulse` / `set_strength` / `adjust_strength` 新增可选字段
  （`target_id`、`cause`、`pulse_name`、`name`、`from_pct`、`to_pct`、
  `delta_pct`），未传时不序列化，向后兼容（感谢 @Kobop1）
- **SDK**：新增 `Agent.wait_ready(timeout)`（阻塞等待握手，失败抛出异常
  由调用方决策）与 `Agent.is_ready()`（非阻塞单次就绪检查）
- **SDK**：测试套件（codec / agent 生命周期 / 消息字段，CI 自动运行）
- **Packer**：构建系统架构（`build_systems.py`），配置按系统独立记忆：
  - `Python - uv` — 清单驱动 vendor、`[tool.dghub].entry` 自动填充、
    可选 PyInstaller exe
  - `(无构建系统)` — 收集目录（产物根）+ pre-build 命令（可独立指定
    执行目录，默认插件目录）+ 附加文件精确/glob 规则收集
- **Packer**：设置页新增「PyPI 镜像源」选项（预置清华/阿里云/中科大），
  vendor 依赖打包时注入 `UV_DEFAULT_INDEX`，全局持久化
- **Packer**：逻辑层测试套件（43 项，CI 在 Windows 运行）

### 变更

- **SDK**：`with Agent(...)` 进入时不再等待握手（保持非阻塞语义），
  需在首次 `poll()` / 发送前显式调用 `wait_ready()`；快速开始示例与
  demo/tetris 已同步更新
- **Packer**：自身依赖管理由 pip + requirements.txt 迁移至 uv
  （pyproject.toml + uv.lock），源码运行命令改为
  `uv sync --project packer` + `uv run --project packer ...`
- **发布流程**：SDK 仅通过 PyPI 分发，GitHub Release 附件不再包含
  wheel；CI 检测 `sdk/python` 无变更时自动跳过 SDK 构建与 PyPI 发布
- demo/tetris 适配新 API 与 uv 项目结构（src 布局 + pyproject.toml）

### 修复

- 后台发送/关闭异常现在会进入 `get_exception()` 队列，不再静默丢失
- Packer 全局状态文件（state.json）改为读-改-写合并，修复设置项互相
  覆盖的问题

## [0.1.3] - 2026-07-27

历史版本，详见 [Releases](https://github.com/curtainsmall/dghub-sdk-toolkit/releases)。

[0.3.0]: https://github.com/curtainsmall/dghub-sdk-toolkit/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/curtainsmall/dghub-sdk-toolkit/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/curtainsmall/dghub-sdk-toolkit/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/curtainsmall/dghub-sdk-toolkit/releases/tag/v0.1.3
