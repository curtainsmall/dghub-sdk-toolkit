# Changelog

本项目的所有重要变更记录在此文件。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。
版本号为 toolkit 发布批次号，Packer 与 SDK 统一使用；SDK 仅在自身有变更
的批次发布至 PyPI（版本跳号为预期行为）。

## [Unreleased]

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

[Unreleased]: https://github.com/curtainsmall/dghub-sdk-toolkit/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/curtainsmall/dghub-sdk-toolkit/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/curtainsmall/dghub-sdk-toolkit/releases/tag/v0.1.3
