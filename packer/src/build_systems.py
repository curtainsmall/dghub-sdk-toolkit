"""构建体系子类：一个构建体系 = 一个类，与 project.json 的命名空间一一对应。

- ``id`` 即配置命名空间键名与类型判别符（"uv" / "generic"）
- 每种语言钦定一个构建体系，下拉文案约定为「语言 - 构建体系」
  （如 "Python - uv"，未来 "C/C++ - CMake"）；generic 为 "(无构建系统)"
- 依赖声明由用户项目自己的管理器维护（如 pyproject.toml），
  Packer 只读清单并 vendor 化，不修改项目源文件
- 新增语言 = 新建子类 + 在 ``BUILD_SYSTEMS`` 注册一行
"""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any, Optional

from exe_builder import build_plugin_exe, _NO_WINDOW


@dataclass
class BuildContext:
    """校验与构建共用的上下文（app.py 组装）。"""

    plugin_dir: Path
    source_dir: Path
    output_dir: Path
    plugin_name: str
    dist_view: Any
    log: Callable[[str], None]
    pypi_index: str = ""  # PyPI 镜像源 URL，空 = 跟随 uv 默认


class BuildError(Exception):
    """产物收集阶段的失败（缺失文件 / 同名冲突），携带错误列表。"""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def _run_logged(cmd: Any, log: Callable[[str], None],
                cwd: Optional[str] = None, shell: bool = False,
                timeout: int = 900,
                env: Optional[dict] = None) -> bool:
    """执行子进程，stdout/stderr 逐行写日志，返回是否成功。"""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=cwd, shell=shell, env=env, creationflags=_NO_WINDOW)
    except FileNotFoundError:
        log(f"[错误] 命令不存在: {cmd}")
        return False
    except subprocess.TimeoutExpired:
        log(f"[错误] 命令超时: {cmd}")
        return False
    for line in (result.stdout or "").splitlines():
        log(f"  {line}")
    for line in (result.stderr or "").splitlines():
        log(f"  {line}")
    return result.returncode == 0


class BuildSystemSupport:
    """构建体系基类：可用性预检、校验、构建步骤与产物清单收集。"""

    id = ""
    label = ""
    dep_manifest_hint = ""  # 依赖清单文件名（UI「依赖来源」展示；空 = 无）

    def check_available(self) -> tuple[bool, str]:
        """工具可用性预检，返回 (可用, 标注文案)。"""
        return True, ""

    def validate(self, ctx: BuildContext) -> list[str]:
        """构建前静态校验，返回错误消息列表（空 = 通过）。"""
        if not ctx.dist_view.get_entry():
            return ["入口文件不能为空"]
        return []

    def build_steps(self, ctx: BuildContext) -> bool:
        """执行体系特有构建步骤（依赖 vendor / pre-build 等），失败返回 False。"""
        return True

    def manifest_entry(self, ctx: BuildContext) -> str:
        """构建产物中 manifest.json 的 entry 值。"""
        return ctx.dist_view.get_entry()

    def collect_output(self, ctx: BuildContext) -> list[tuple[Path, str]]:
        """收集产物清单 [(源文件路径, 包内路径)]；缺失/冲突抛 BuildError。

        在 build_steps 之后调用（generic 的文件可能由 pre-build 生成）。
        """
        return []


# ---------------------------------------------------------------------------
# Python 系（uv / pip）：从源码构建，依赖清单由项目管理器维护
# ---------------------------------------------------------------------------

class _PythonBase(BuildSystemSupport):
    """Python 系共性：.py entry 校验、清单驱动 vendor、可选 PyInstaller exe。

    项目根锚点 = 用户选定的依赖清单文件所在目录（ctx.source_dir，由
    app.py 派生；未选清单时回退插件目录）。
    """

    def _vendor_cmd(self, manifest: Path, vendor_dir: Path) -> list[str]:
        """返回把清单依赖安装到 vendor_dir 的命令。"""
        raise NotImplementedError

    def validate(self, ctx: BuildContext) -> list[str]:
        entry = ctx.dist_view.get_entry()
        if not entry:
            return ["入口文件不能为空"]
        if not entry.lower().endswith(".py"):
            return [f"{self.label} 体系的入口必须是 .py 文件: {entry}，"
                    "如为已构建产物请将构建体系切换为「(无构建系统)」"]
        if not (ctx.source_dir / entry).is_file():
            return [f"入口文件不存在: {entry}"]
        return []

    def build_steps(self, ctx: BuildContext) -> bool:
        # 依赖 vendor：读用户选定的清单安装到临时 vendor/（不改项目文件）
        manifest_path = ctx.dist_view.get_manifest()
        if not manifest_path:
            ctx.log(f"未选择依赖清单（{self.dep_manifest_hint}），跳过依赖打包"
                    "（无第三方依赖时属正常情形）")
        else:
            manifest = Path(manifest_path)
            if not manifest.is_file():
                ctx.log(f"[错误] 依赖清单不存在: {manifest}")
                return False
            ctx.log(f"依赖来源: {manifest}，安装到 vendor/ ...")
            vendor_dir = ctx.output_dir / "vendor"
            env = None
            if ctx.pypi_index:
                env = {**os.environ, "UV_DEFAULT_INDEX": ctx.pypi_index}
                ctx.log(f"使用 PyPI 镜像源: {ctx.pypi_index}")
            if not _run_logged(self._vendor_cmd(manifest, vendor_dir),
                               ctx.log, cwd=str(ctx.source_dir), env=env):
                ctx.log("[错误] 依赖打包失败")
                return False
            ctx.log("依赖打包完成（清单内容不做逐包过滤，由项目清单自行控制；"
                    "dghub-sdk 由「包含 dghub-sdk」选项单独注入）")

        # 可选：构建独立 exe（PyInstaller）
        if ctx.dist_view.get_build_exe():
            ctx.log("构建 exe...")
            ok = build_plugin_exe(
                plugin_dir=str(ctx.plugin_dir),
                source_dir=str(ctx.source_dir),
                include_dghub_sdk=ctx.dist_view.get_include_sdk(),
                log_callback=ctx.log,
                output_dir=str(ctx.output_dir),
                entry=ctx.dist_view.get_entry(),
            )
            if not ok:
                ctx.log("[错误] exe 构建失败")
                return False
            # 清理 PyInstaller 残留（插件目录内，构建后即清）
            for leftover in ctx.plugin_dir.glob("*.spec"):
                leftover.unlink()
            build_dir = ctx.plugin_dir / "build"
            if build_dir.is_dir():
                import shutil
                shutil.rmtree(build_dir)
            ctx.log("exe 构建完成")
        return True

    def manifest_entry(self, ctx: BuildContext) -> str:
        if ctx.dist_view.get_build_exe():
            return f"{ctx.plugin_name}.exe"
        return ctx.dist_view.get_entry()

    def collect_output(self, ctx: BuildContext) -> list[tuple[Path, str]]:
        files: list[tuple[Path, str]] = []
        if ctx.dist_view.get_build_exe():
            exe_path = ctx.output_dir / f"{ctx.plugin_name}.exe"
            if not exe_path.is_file():
                raise BuildError([f"exe 产物不存在: {exe_path}"])
            files.append((exe_path, exe_path.name))
        else:
            entry_src = ctx.source_dir / ctx.dist_view.get_entry()
            if not entry_src.is_file():
                raise BuildError([f"入口文件不存在: {entry_src}"])
            files.append((entry_src, entry_src.name))
            vendor_src = ctx.output_dir / "vendor"
            if vendor_src.is_dir():
                for f in vendor_src.rglob("*"):
                    if f.is_file():
                        files.append(
                            (f, f.relative_to(ctx.output_dir).as_posix()))
        return files


class UvSystem(_PythonBase):
    """Python 钦定体系 uv：清单为 pyproject.toml（也可选 requirements.txt，
    uv 同样能消费）。"""

    id = "uv"
    label = "Python - uv"
    dep_manifest_hint = "pyproject.toml"

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

    def _vendor_cmd(self, manifest: Path, vendor_dir: Path) -> list[str]:
        # uv 支持从 pyproject.toml / requirements 格式文件直接解析依赖
        return ["uv", "pip", "install", "--target", str(vendor_dir),
                "-r", str(manifest)]


# ---------------------------------------------------------------------------
# (无构建系统)：不使用任何构建器，直接打包原始文件
# ---------------------------------------------------------------------------

class GenericSupport(BuildSystemSupport):
    """(无构建系统)：可选 pre-build 命令后，按清单/规则打包工作目录内文件。"""

    id = "generic"
    label = "(无构建系统)"

    def validate(self, ctx: BuildContext) -> list[str]:
        # 仅静态校验；entry / 附加文件存在性延迟到 pre-build 之后
        # （collect_output 内），因为它们可能由 pre-build 生成
        if not ctx.dist_view.get_entry():
            return ["入口文件不能为空"]
        return []

    def build_steps(self, ctx: BuildContext) -> bool:
        cmd = ctx.dist_view.get_pre_build().strip()
        if not cmd:
            ctx.log("(无构建系统)：无 pre-build 命令，直接收集文件")
            return True
        ctx.log(f"执行 pre-build（工作目录 {ctx.source_dir}）: {cmd}")
        if not _run_logged(cmd, ctx.log, cwd=str(ctx.source_dir),
                           shell=True):
            ctx.log("[错误] pre-build 命令失败（非零返回码）")
            return False
        ctx.log("pre-build 完成")
        return True

    def collect_output(self, ctx: BuildContext) -> list[tuple[Path, str]]:
        errors: list[str] = []
        files: list[tuple[Path, str]] = []
        entry = ctx.dist_view.get_entry()
        entry_src = ctx.source_dir / entry
        if entry_src.is_file():
            # entry 保留相对路径子目录结构
            files.append((entry_src, Path(entry).as_posix()))
        else:
            errors.append(f"入口文件不存在: {entry}")

        # (dest, 包内文件名) → 相对源路径；精确条目优先，规则匹配去重
        dest_names = {"root": "根目录", "vendor": "vendor/"}
        seen: dict[tuple[str, str], str] = {}

        def _add(rel: str, dest: str) -> None:
            if rel == entry:
                return  # entry 不重复收集
            name = Path(rel).name
            key = (dest, name)
            if key in seen:
                if seen[key] != rel:
                    errors.append(
                        f"附加文件同名冲突: {seen[key]} 与 {rel}"
                        f"（同为{dest_names[dest]}）")
                return
            seen[key] = rel
            arc = name if dest == "root" else f"vendor/{name}"
            files.append((ctx.source_dir / rel, arc))

        items = ctx.dist_view.get_extra_files()
        # 精确条目优先收集
        for item in items:
            if "path" in item:
                if (ctx.source_dir / item["path"]).is_file():
                    _add(item["path"], item["dest"])
                else:
                    errors.append(f"附加文件不存在: {item['path']}")
        # 规则条目构建时求值（pre-build 之后，生成物可被匹配）
        for item in items:
            if "pattern" in item:
                matched = evaluate_pattern(ctx.source_dir, item["pattern"])
                if not matched:
                    ctx.log(f"[提示] 规则无匹配: {item['pattern']}")
                for rel in matched:
                    _add(rel, item["dest"])

        if errors:
            raise BuildError(errors)
        return files


def evaluate_pattern(workdir: Path, pattern: str) -> list[str]:
    """对工作目录求值 glob 规则，返回相对路径列表（仅文件，排序）。"""
    try:
        return sorted(
            p.relative_to(workdir).as_posix()
            for p in workdir.glob(pattern) if p.is_file())
    except (ValueError, OSError):
        return []


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


# 注册表：键 = 构建体系 id = 配置命名空间键名（每语言钦定一个体系）
BUILD_SYSTEMS: dict[str, BuildSystemSupport] = {
    "uv": UvSystem(),
    "generic": GenericSupport(),
}
