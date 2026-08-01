"""pre-build 处理器体系：抽象契约 + 两个实现 + 注册表。

处理器 = 阶段 1（把源码变成可打包产物）的可插拔实现，由 project.json 的
``producer`` 字段显式单选（"" 无 / "python" / "command"）。一切语言相关
解析（清单识别、[tool.dghub].entry 读取、probe、deduce）都在处理器内，
GUI 与管线不内置任何语言知识。

抽象契约（Producer 九项能力）：身份、设置字段、启用、清单识别、
探测、预检、校验、推导、执行。处理器不推断 Builder（deduce 只是建议）、
不读顶层 entry 之外的信息、不持久化、不接触 GUI。
"""

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from backend.build_control import Canceller
from backend.exe_builder import build_plugin_exe
from backend.logbus import Logger
from backend.winflags import _NO_WINDOW


@dataclass
class ProducerContext:
    """处理器运行时上下文（run 时由管线组装）。"""

    plugin_dir: Path
    source_dir: Path
    output_dir: Path
    plugin_name: str
    cfg: dict[str, Any]          # 处理器设置字段（producer 相关字段）
    entry: str                   # 顶层 entry（阶段 1 输入）
    log: Logger
    pypi_index: str = ""
    canceller: Optional[Canceller] = None


def run_logged(cmd: Any, logger: Logger, source: str,
               cwd: Optional[str] = None, shell: bool = False,
               timeout: int = 900,
               env: Optional[dict] = None,
               canceller: Optional[Canceller] = None) -> bool:
    """执行子进程（可取消），输出以来源分隔块记录，返回是否成功。"""
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=cwd, shell=shell, env=env,
            creationflags=_NO_WINDOW)
    except FileNotFoundError:
        logger.error(f"命令不存在: {cmd}")
        return False
    if canceller is not None:
        canceller.set_proc(proc)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
        logger.error(f"命令超时: {cmd}")
        logger.external(source, (out or "").splitlines(), proc.returncode)
        return False
    finally:
        if canceller is not None:
            canceller.set_proc(None)
    logger.external(source, (out or "").splitlines(), proc.returncode)
    if canceller is not None and canceller.cancelled:
        logger.warning(f"{source} 已取消")
        return False
    return proc.returncode == 0


class Producer:
    """pre-build 处理器抽象契约（所有处理器共有的接口形状）。"""

    id = ""
    label = ""
    description = ""
    # 设置字段 schema：{field: {"label": str, "type": "str"|"bool",
    #                            "default": Any, "required": bool}}
    fields: dict[str, dict[str, Any]] = {}

    def enabled(self, cfg: dict[str, Any]) -> bool:
        """由显式 producer 选择字段决定；缺必要字段由 validate 兜底。"""
        return bool(cfg)

    def is_known_manifest(self, filename: str) -> bool:
        """所选清单是否本处理器可识别（无清单概念恒 False）。"""
        return False

    def probe(self, plugin_dir: Path) -> Optional[dict[str, Any]]:
        """探测项目，建议初始配置（无探测能力恒 None）。"""
        return None

    def check_available(self) -> tuple[bool, str]:
        """工具可用性预检，返回 (可用, 标注文案)。"""
        return True, ""

    def validate(self, cfg: dict[str, Any], entry: str,
                 source_dir: Path) -> list[str]:
        """静态校验处理器设置，返回错误消息列表（空 = 通过）。"""
        errors: list[str] = []
        for fname, spec in self.fields.items():
            if spec.get("required") and not cfg.get(fname):
                errors.append(f"已选择 {self.label} 处理器，"
                              f"但未填写{spec.get('label', fname)}")
        return errors

    def deduce(self, cfg: dict[str, Any],
                plugin_name: str = "") -> Optional[list[dict[str, Any]]]:
        """检查设置是否足以推导 Builder 条目；返回建议条目或 None。"""
        return None

    def run(self, ctx: ProducerContext) -> bool:
        """执行阶段 1 工作，产出文件；失败返回 False。"""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# CommandProducer：用户自定义命令
# ---------------------------------------------------------------------------

class CommandProducer(Producer):
    """执行用户 shell 命令产出任意文件；产物位置不可预测，
    Builder 条目由用户声明（deduce 恒 None）。"""

    id = "command"
    label = "自定义命令"
    description = "构建前执行用户命令（如编译、生成资源），产物由打包内容声明"
    fields = {
        "pre_build": {"label": "预构建命令", "type": "str",
                      "default": "", "required": True},
        "exec_dir": {"label": "执行目录", "type": "str",
                     "default": "", "required": False},
    }

    def enabled(self, cfg: dict[str, Any]) -> bool:
        return bool(cfg.get("pre_build"))

    def probe(self, plugin_dir: Path) -> Optional[dict[str, Any]]:
        return None

    def deduce(self, cfg: dict[str, Any],
                plugin_name: str = "") -> Optional[list[dict[str, Any]]]:
        return None

    def run(self, ctx: ProducerContext) -> bool:
        cmd = (ctx.cfg.get("pre_build") or "").strip()
        if not cmd:
            ctx.log.error("预构建命令为空")
            return False
        exec_dir = ctx.cfg.get("exec_dir") or str(ctx.source_dir)
        ctx.log.info(f"执行预构建命令（执行目录 {exec_dir}）: {cmd}")
        return run_logged(cmd, ctx.log, "pre-build", cwd=exec_dir,
                          shell=True, canceller=ctx.canceller)


# ---------------------------------------------------------------------------
# PythonProducer：uv 依赖下载 + PyInstaller onedir
# ---------------------------------------------------------------------------

# uv 可识别的依赖清单类型
_PY_MANIFESTS = ("pyproject.toml", "setup.py", "setup.cfg", "requirements*.txt")


class PythonProducer(Producer):
    """uv 按清单下载依赖到 .deps → PyInstaller onedir 打包（含 SDK 可选）。

    产物约定：``out_dir/<name>/`` onedir 树（固定位置，管线整树收集）。
    """

    id = "python"
    label = "Python (uv + PyInstaller)"
    description = ("按依赖清单自动下载依赖并打包为自包含 exe"
                   "（uv 下载 + PyInstaller onedir）")
    fields = {
        "manifest": {"label": "依赖清单", "type": "str",
                     "default": "", "required": True},
        "include_sdk": {"label": "包含 dghub-sdk", "type": "bool",
                        "default": True, "required": False},
    }

    def enabled(self, cfg: dict[str, Any]) -> bool:
        return bool(cfg.get("manifest"))

    def is_known_manifest(self, filename: str) -> bool:
        name = filename.lower()
        return name in ("pyproject.toml", "setup.py", "setup.cfg") or (
            name.startswith("requirements") and name.endswith(".txt"))

    def probe(self, plugin_dir: Path) -> Optional[dict[str, Any]]:
        """探测 pyproject.toml → 建议 manifest / entry / include_sdk。"""
        pyproject = plugin_dir / "pyproject.toml"
        if not pyproject.is_file():
            return None
        suggest: dict[str, Any] = {
            "manifest": "pyproject.toml",
            "include_sdk": True,
        }
        entry = read_tool_dghub_entry(pyproject)
        if entry:
            suggest["entry"] = entry
        return suggest

    def check_available(self) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["uv", "--version"], capture_output=True, text=True,
                timeout=10, creationflags=_NO_WINDOW)
            if result.returncode == 0:
                return True, "需要 uv"
        except Exception:
            pass
        return False, "未检测到 uv，请 pip install uv"

    def validate(self, cfg: dict[str, Any], entry: str,
                 source_dir: Path) -> list[str]:
        errors = super().validate(cfg, entry, source_dir)
        manifest = cfg.get("manifest", "")
        if manifest and not self.is_known_manifest(Path(manifest).name):
            errors.append(f"无法识别的依赖清单: {Path(manifest).name}"
                          "（支持 pyproject.toml / setup.py / setup.cfg / "
                          "requirements*.txt）")
        if not entry:
            errors.append("入口文件不能为空")
        elif not entry.lower().endswith(".py"):
            errors.append(f"Python 处理器的入口必须是 .py 文件: {entry}，"
                          "如为已构建产物请将处理器设为「自定义命令」")
        elif not (source_dir / entry).is_file():
            errors.append(f"入口文件不存在: {entry}")
        return errors

    def deduce(self, cfg: dict[str, Any],
                plugin_name: str = "") -> Optional[list[dict[str, Any]]]:
        """manifest 已选 → 推导 entry 条目（产物名 = <插件名>.exe）。"""
        if not cfg.get("manifest"):
            return None
        if not plugin_name:
            return None
        return [{"path": f"{plugin_name}.exe", "tags": ["entry"]}]

    def run(self, ctx: ProducerContext) -> bool:
        manifest = ctx.cfg.get("manifest", "")
        if not manifest:
            ctx.log.error("依赖清单为空")
            return False
        manifest_path = Path(ctx.source_dir) / manifest
        if not manifest_path.is_file():
            ctx.log.error(f"依赖清单不存在: {manifest_path}")
            return False

        # 1) uv 按清单安装依赖到 .deps（中间产物，构建后清理）
        deps_dir = ctx.output_dir / ".deps"
        ctx.log.info(f"依赖来源: {manifest}，安装到 .deps/ ...")
        env = None
        if ctx.pypi_index:
            env = {**os.environ, "UV_DEFAULT_INDEX": ctx.pypi_index}
            ctx.log.detail(f"使用 PyPI 镜像源: {ctx.pypi_index}")
        ok = run_logged(
            ["uv", "pip", "install", "--target", str(deps_dir),
             "-r", str(manifest_path)],
            ctx.log, "uv", cwd=str(ctx.source_dir),
            env=env, canceller=ctx.canceller)
        if not ok:
            ctx.log.error("依赖打包失败")
            return False
        ctx.log.info("依赖打包完成")

        # 2) PyInstaller onedir 打包（依赖 + 项目根散装模块进 exe）
        ctx.log.info("构建 exe...")
        ok = build_plugin_exe(
            plugin_dir=str(ctx.plugin_dir),
            source_dir=str(ctx.source_dir),
            include_dghub_sdk=bool(ctx.cfg.get("include_sdk", True)),
            logger=ctx.log,
            output_dir=str(ctx.output_dir),
            entry=ctx.entry,
            dep_dir=str(deps_dir),
            canceller=ctx.canceller,
        )
        if not ok:
            ctx.log.error("exe 构建失败")
            return False

        # 3) 清理 PyInstaller 残留（插件目录内，构建后即清）
        for leftover in ctx.plugin_dir.glob("*.spec"):
            leftover.unlink()
        build_dir = ctx.plugin_dir / "build"
        if build_dir.is_dir():
            shutil.rmtree(build_dir, ignore_errors=True)
        ctx.log.info("exe 构建完成")
        return True


def read_tool_dghub_entry(manifest: Path) -> str:
    """读 pyproject.toml 的 [tool.dghub].entry（可选约定，仅读不写）。

    不存在、非 pyproject.toml 或解析失败均返回空串。
    """
    if manifest.name != "pyproject.toml" or not manifest.is_file():
        return ""
    try:
        import tomllib
        with open(manifest, "rb") as f:
            data = tomllib.load(f)
        entry = data.get("tool", {}).get("dghub", {}).get("entry", "")
        return entry if isinstance(entry, str) else ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------

PRODUCERS: dict[str, Producer] = {
    "python": PythonProducer(),
    "command": CommandProducer(),
}

# 处理器选项（GUI 下拉 / config 校验）：("" 无) 优先于具体处理器
PRODUCER_CHOICES: tuple[tuple[str, str], ...] = (
    ("", "无"),
    ("python", "Python (uv + PyInstaller)"),
    ("command", "自定义命令"),
)


def get_producer(producer_id: str) -> Optional[Producer]:
    """按 id 取处理器（空串或未知返回 None）。"""
    if not producer_id:
        return None
    return PRODUCERS.get(producer_id)
