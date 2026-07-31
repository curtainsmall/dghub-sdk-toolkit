"""Packer CLI：子命令分发、stdout 分级日志、构建上下文组装。

以 `.dghub-sdk/` 为项目数据源，复用后端构建内核（与 GUI 同一条 run_build 路径）。
禁止 import customtkinter：CLI 需能在无显示环境（CI）运行。
"""

import argparse
import json
import signal
import sys
from pathlib import Path
from typing import Optional

from backend import settings_store
from backend.build_control import Canceller
from backend.build_runner import run_build
from backend.build_systems import (BUILD_SYSTEMS, BuildContext, BuildError,
                                   read_tool_dghub_entry)
from backend.input_apply import apply_input
from backend.logbus import Logger
from backend.manifest_validator import validate_manifest
from backend.project_manager import (ProjectManager, UnsupportedFormatError,
                                      project_exists)
from cli.cli_view import CliDistView

try:
    from backend._version import __version__ as APP_VERSION
except ImportError:
    APP_VERSION = "dev"

# 退出码
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_VALIDATE = 3
EXIT_BUILD = 4
EXIT_CANCELLED = 130

# 着色级别 → ANSI 前景色（仅 error/warning/success 着色）
_ANSI = {"error": "\033[31m", "warning": "\033[33m", "success": "\033[32m"}
_ANSI_RESET = "\033[0m"


def make_logger(no_color: bool, verbose: bool, quiet: bool) -> Logger:
    """构造 stdout 分级日志器。

    - quiet：仅 error / warning / success；verbose：额外显示 detail。
    - 着色仅 error/warning/success；sep/external 原样（external 缩进），info/detail 默认色。
    - error 走 stderr，其余走 stdout。
    """
    def sink(text: str, level: str) -> None:
        if quiet and level not in ("error", "warning", "success"):
            return
        if level == "detail" and not verbose:
            return
        line = text
        if level == "external":
            line = f"  {text}"
        color = _ANSI.get(level)
        if color and not no_color:
            line = f"{color}{line}{_ANSI_RESET}"
        stream = sys.stderr if level == "error" else sys.stdout
        print(line, file=stream)
    return Logger(sink)


def _install_sigint(canceller: Canceller) -> None:
    """Ctrl+C 触发取消（终止子进程树），而非直接抛 KeyboardInterrupt。"""
    def handler(_sig, _frame):
        canceller.cancel()
    try:
        signal.signal(signal.SIGINT, handler)
    except Exception:
        pass


def _load_project(plugin_dir: str, logger: Logger):
    """加载项目：返回 (pm, project, bs_id)；缺 `.dghub-sdk/` 或格式不兼容返回 None。"""
    if not project_exists(plugin_dir):
        logger.error(f"未找到 Packer 项目（缺少 .dghub-sdk/）: {plugin_dir}")
        logger.info("请先运行 `packer init` 或用 GUI 配置该目录")
        return None
    pm = ProjectManager(plugin_dir, log=logger)
    try:
        project = pm.read_project()
    except UnsupportedFormatError as exc:
        logger.error(str(exc))
        return None
    bs_id = project.get("build_system", "uv")
    if bs_id not in BUILD_SYSTEMS:
        logger.error(f"未知构建系统: {bs_id}")
        return None
    return pm, project, bs_id


def _make_ctx(pm: ProjectManager, project: dict, bs_id: str, logger: Logger,
              canceller: Optional[Canceller], output_override: str,
              pypi_override: Optional[str]) -> tuple[BuildContext, CliDistView]:
    """按 GUI 同款语义组装 BuildContext（源码根/输出目录/镜像源）。"""
    dist = CliDistView(pm, bs_id)
    plugin_dir = pm.plugin_dir
    source_dir = Path(dist.get_source_dir())
    # 输出目录基准区分来源：-o 命令行参数相对 cwd（CLI 惯例）；
    # project.json 的 output_dir 相对插件目录（可移植性约定）
    if output_override:
        output_dir = Path(output_override).resolve()
    else:
        out = project.get("output_dir", "")
        output_dir = Path(pm.to_absolute(out)) if out else plugin_dir / "output"
    if pypi_override is not None:
        pypi = pypi_override
    else:
        pypi = settings_store.get_state("pypi_index", "")
    ctx = BuildContext(
        plugin_dir=plugin_dir,
        source_dir=source_dir,
        output_dir=output_dir,
        plugin_name=plugin_dir.name,
        dist_view=dist,
        log=logger,
        pypi_index=pypi,
        canceller=canceller,
    )
    return ctx, dist


def _validate(pm: ProjectManager, project: dict, bs_id: str,
              logger: Logger) -> list[str]:
    """校验插件信息 + 构建配置，返回全部错误（空 = 通过）。"""
    errors: list[str] = []
    for msg in validate_manifest(pm.read_manifest()):
        errors.append(f"信息 → {msg}")
    ctx, _ = _make_ctx(pm, project, bs_id, logger, None, "", None)
    for msg in BUILD_SYSTEMS[bs_id].validate(ctx):
        errors.append(f"构建 → {msg}")
    return errors


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------

def cmd_build(args, logger: Logger) -> int:
    loaded = _load_project(args.dir, logger)
    if loaded is None:
        return EXIT_USAGE
    pm, project, bs_id = loaded

    logger.info("开始校验")
    errors = _validate(pm, project, bs_id, logger)
    if errors:
        for msg in errors:
            logger.error(msg)
        return EXIT_VALIDATE
    logger.info("校验通过")

    canceller = Canceller()
    _install_sigint(canceller)
    ctx, _ = _make_ctx(pm, project, bs_id, logger, canceller,
                       args.output or "", args.pypi_index)
    ctx.output_dir.mkdir(parents=True, exist_ok=True)
    target = args.target or project.get("target", "zip")
    manifest_data = pm.read_manifest()
    bs = BUILD_SYSTEMS[bs_id]
    try:
        artifact = run_build(ctx, bs, manifest_data, target)
    except BuildError as be:
        for msg in be.errors:
            logger.error(msg)
        return EXIT_BUILD
    if canceller.cancelled:
        logger.warning("构建已取消")
        return EXIT_CANCELLED
    if artifact is None:
        return EXIT_BUILD
    return EXIT_OK


def cmd_validate(args, logger: Logger) -> int:
    loaded = _load_project(args.dir, logger)
    if loaded is None:
        return EXIT_USAGE
    pm, project, bs_id = loaded
    errors = _validate(pm, project, bs_id, logger)
    if errors:
        for msg in errors:
            logger.error(msg)
        return EXIT_VALIDATE
    logger.success("校验通过")
    return EXIT_OK


def cmd_init(args, logger: Logger) -> int:
    plugin_dir = args.dir
    if project_exists(plugin_dir) and not args.force:
        logger.warning(f".dghub-sdk/ 已存在，无需初始化（如需重置用 --force）: {plugin_dir}")
        return EXIT_OK
    pm = ProjectManager(plugin_dir, log=logger)
    project = pm.read_project()

    # 确定构建系统：--build-system 显式指定，否则智能探测
    has_pyproject = (Path(plugin_dir) / "pyproject.toml").is_file()
    if args.build_system:
        system = args.build_system
    else:
        system = "uv" if has_pyproject else "generic"
    project["build_system"] = system
    pm.write_project(project)

    # 智能预填：uv + 存在 pyproject.toml → manifest 指向它，并试填入口
    if system == "uv" and has_pyproject:
        pm.set_bs_config("uv", "manifest", "pyproject.toml")
        auto = read_tool_dghub_entry(Path(plugin_dir) / "pyproject.toml")
        if auto:
            pm.set_bs_config("uv", "entry", auto)
            logger.info(f"已从 [tool.dghub] 自动填充入口: {auto}")

    # 写 manifest.json（项目标志文件，project_exists 据此判定）
    pm.write_manifest(pm.read_manifest())
    logger.success(f"已初始化 Packer 项目（构建系统: {system}）: "
                   f"{(Path(plugin_dir) / '.dghub-sdk').as_posix()}")
    return EXIT_OK


def cmd_apply(args, logger: Logger) -> int:
    plugin_dir = args.dir
    if not project_exists(plugin_dir):
        logger.error(f"未找到 Packer 项目（缺少 .dghub-sdk/）: {plugin_dir}")
        logger.info("请先运行 `packer init`（apply 不会自动创建项目）")
        return EXIT_USAGE
    input_file = Path(args.file) if args.file \
        else Path(plugin_dir) / "packer-input.json"
    if not input_file.is_file():
        logger.error(f"输入文件不存在: {input_file}")
        return EXIT_USAGE
    try:
        entries = json.loads(input_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error(f"输入文件解析失败（需纯 JSON）: {exc}")
        return EXIT_USAGE
    if not isinstance(entries, dict):
        logger.error("输入文件根必须为 JSON 对象")
        return EXIT_USAGE

    if args.dry_run:
        logger.info("[dry-run] 将应用以下键（不落盘）:")
        for section in ("plugin", "build", "config_schema"):
            if section in entries:
                val = entries[section]
                keys = list(val.keys()) if isinstance(val, dict) else val
                logger.info(f"  {section}: {keys}")
        return EXIT_OK

    pm = ProjectManager(plugin_dir, log=logger)
    for notice in apply_input(pm, entries):
        logger.warning(notice)
    logger.success(f"已应用输入清单到 .dghub-sdk/: {input_file}")
    return EXIT_OK


def cmd_export(args, logger: Logger) -> int:
    plugin_dir = args.dir
    if not project_exists(plugin_dir):
        logger.error(f"未找到 Packer 项目（缺少 .dghub-sdk/）: {plugin_dir}")
        return EXIT_USAGE
    out_file = Path(args.file) if args.file \
        else Path(plugin_dir) / "packer-input.json"
    if out_file.exists() and not args.force:
        logger.error(f"文件已存在（用 --force 覆盖）: {out_file}")
        return EXIT_USAGE
    pm = ProjectManager(plugin_dir, log=logger)
    project = pm.read_project()
    manifest = pm.read_manifest()
    system = project.get("build_system", "uv")
    cfg = pm.get_bs_config(system)

    build: dict = {"system": system, "target": project.get("target", "zip")}
    if project.get("output_dir"):
        build["output_dir"] = project["output_dir"]
    if system == "uv":
        build["manifest"] = cfg.get("manifest", "")
        build["build_exe"] = cfg.get("build_exe", True)
        build["include_sdk"] = cfg.get("include_sdk", True)
    else:
        build["source_dir"] = cfg.get("source_dir", "")
        build["pre_build"] = cfg.get("pre_build", "")
        build["exec_dir"] = cfg.get("exec_dir", "")
        build["files"] = cfg.get("extra_files", [])

    plugin: dict = {k: manifest.get(k, "")
                    for k in ("id", "name", "version", "author", "description")}
    plugin["entry"] = cfg.get("entry", "")
    if "capabilities" in manifest:
        plugin["capabilities"] = manifest["capabilities"]

    data = {"plugin": plugin, "build": build}
    if "config_schema" in manifest:
        data["config_schema"] = manifest["config_schema"]
    try:
        out_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.error(f"写入失败: {exc}")
        return EXIT_USAGE
    logger.success(f"已导出输入清单: {out_file}")
    return EXIT_OK


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------

def _global_parser() -> argparse.ArgumentParser:
    """全局标志父 parser：供顶层与各子命令共用，使其前后置皆可。

    用 ``argparse.SUPPRESS`` 作默认值，避免子 parser 的默认覆盖顶层已解析值。
    """
    g = argparse.ArgumentParser(add_help=False)
    g.add_argument("--no-color", action="store_true", default=argparse.SUPPRESS,
                   help="禁用日志 ANSI 着色（重定向 / CI 友好）")
    g.add_argument("-v", "--verbose", action="store_true",
                   default=argparse.SUPPRESS, help="显示更详尽的日志（含 detail）")
    g.add_argument("-q", "--quiet", action="store_true",
                   default=argparse.SUPPRESS, help="仅显示警告 / 错误 / 结果")
    return g


def build_parser() -> argparse.ArgumentParser:
    g = _global_parser()
    parser = argparse.ArgumentParser(
        prog="packer",
        description="DGHub 插件打包工具（命令行）",
        parents=[g])
    # -V/--version 为「打印版本即退出」的元标志，仅顶层
    parser.add_argument("-V", "--version", action="version",
                        version=f"DGHub Packer {APP_VERSION}")

    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", parents=[g], help="构建插件（读 .dghub-sdk/）")
    p_build.add_argument("dir", nargs="?", default=".", help="项目目录")
    p_build.add_argument("-o", "--output", help="覆盖输出目录")
    p_build.add_argument("--target", choices=["zip", "folder"],
                         help="覆盖发布目标")
    p_build.add_argument("--pypi-index", help="覆盖依赖 vendor 的 PyPI 镜像")
    p_build.set_defaults(func=cmd_build)

    p_val = sub.add_parser("validate", parents=[g], help="仅校验不构建")
    p_val.add_argument("dir", nargs="?", default=".", help="项目目录")
    p_val.set_defaults(func=cmd_validate)

    p_init = sub.add_parser("init", parents=[g], help="初始化 .dghub-sdk/（建 Packer 项目）")
    p_init.add_argument("dir", nargs="?", default=".", help="项目目录")
    p_init.add_argument("--build-system", choices=["uv", "generic"],
                        help="显式指定构建系统（覆盖智能探测）")
    p_init.add_argument("--force", action="store_true",
                        help=".dghub-sdk/ 已存在时也重置为默认")
    p_init.set_defaults(func=cmd_init)

    p_apply = sub.add_parser("apply", parents=[g],
                             help="应用 packer-input.json 到 .dghub-sdk/")
    p_apply.add_argument("dir", nargs="?", default=".", help="项目目录")
    p_apply.add_argument("-f", "--file", help="输入文件路径（默认 <dir>/packer-input.json）")
    p_apply.add_argument("--dry-run", action="store_true",
                         help="只打印将写入的改动，不落盘")
    p_apply.set_defaults(func=cmd_apply)

    p_export = sub.add_parser("export", parents=[g],
                              help="从 .dghub-sdk/ 导出 packer-input.json")
    p_export.add_argument("dir", nargs="?", default=".", help="项目目录")
    p_export.add_argument("-f", "--file", help="输出路径（默认 <dir>/packer-input.json）")
    p_export.add_argument("--force", action="store_true",
                          help="覆盖已存在文件")
    p_export.set_defaults(func=cmd_export)

    return parser


def dispatch(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # 全局标志用 SUPPRESS 默认，未提供时属性缺失 → getattr 回退
    logger = make_logger(getattr(args, "no_color", False),
                         getattr(args, "verbose", False),
                         getattr(args, "quiet", False))
    return args.func(args, logger)
