"""packer-input.json 输入回放：把「输入清单」按 GUI 输入语义应用到 `.dghub-sdk/`。

输入清单是**可选**的无 GUI 配置手段；apply 后落盘为项目规范状态（等同手动在
GUI 里逐项输入）。仅执行**数据副作用**（视觉副作用属 GUI）。纯 JSON，无注释。
"""

from pathlib import Path
from typing import Any

from backend.build_systems import BUILD_SYSTEMS, read_tool_dghub_entry
from backend.project_manager import ProjectManager

# 各命名空间接受的 build.* 键（路径类单独处理）
_UV_FLAGS = ("build_exe", "include_sdk")
_GENERIC_STR = ("pre_build",)


def _store_path(pm: ProjectManager, value: str) -> str:
    """把输入路径归一为「相对插件目录」的存储形式。

    绝对路径 → to_relative；相对路径视为相对插件目录，原样存 posix。
    """
    if not value:
        return ""
    p = Path(value)
    if p.is_absolute():
        return pm.to_relative(value)
    return p.as_posix()


def _fmt(value: Any) -> str:
    """把值格式化为简短可读形式（dict/list 只报数量，避免刷屏）。"""
    if isinstance(value, dict):
        return f"{{{len(value)} 项}}"
    if isinstance(value, list):
        return f"[{len(value)} 项]"
    return str(value)


def apply_input(pm: ProjectManager,
                entries: dict[str, Any]) -> tuple[list[str], list[str]]:
    """应用输入清单到 `.dghub-sdk/`，返回 (已应用字段列表, 告警/提示列表)。

    映射：plugin.* → manifest（entry 例外，入 bs 命名空间）；build.system →
    当前构建系统；build.* → 对应命名空间；config_schema → manifest。
    """
    applied: list[str] = []
    notices: list[str] = []
    plugin = entries.get("plugin") or {}
    build = entries.get("build") or {}
    config_schema = entries.get("config_schema")

    def _set_bs(ns: str, key: str, new: Any, label: str) -> None:
        """写入 bs 命名空间键；仅当值较原值**有变化**时记入 applied。"""
        old = pm.get_bs_config(ns).get(key)
        pm.set_bs_config(ns, key, new)
        if new != old:
            applied.append(f"{label} = {_fmt(new)}")

    project = pm.read_project()

    # 1) 构建系统 + 插件级键（仅记变化项；set-to-default 因异于原值同样算变化）
    old_system = project.get("build_system")
    system = build.get("system", old_system or "uv")
    if system not in BUILD_SYSTEMS:
        notices.append(f"未知构建系统 '{system}'，保持原值")
        system = old_system or "uv"
    project["build_system"] = system
    if system != old_system:
        applied.append(f"build.system = {system}")
    if "target" in build:
        if build["target"] != project.get("target"):
            applied.append(f"build.target = {build['target']}")
        project["target"] = build["target"]
    if "output_dir" in build:
        stored = _store_path(pm, build["output_dir"])
        if stored != project.get("output_dir"):
            applied.append(f"build.output_dir = {stored}")
        project["output_dir"] = stored
    pm.write_project(project)

    # 2) manifest 字段（id/name/version/author/description/capabilities/config_schema）
    manifest = pm.read_manifest()
    for key in ("id", "name", "version", "author", "description"):
        if key in plugin:
            if plugin[key] != manifest.get(key):
                applied.append(f"plugin.{key} = {_fmt(plugin[key])}")
            manifest[key] = plugin[key]
    if "capabilities" in plugin:
        if plugin["capabilities"] != manifest.get("capabilities"):
            applied.append(f"plugin.capabilities = {_fmt(plugin['capabilities'])}")
        manifest["capabilities"] = plugin["capabilities"]
    if config_schema is not None:
        if config_schema != manifest.get("config_schema"):
            applied.append(f"config_schema = {_fmt(config_schema)}")
        manifest["config_schema"] = config_schema
    pm.write_manifest(manifest)

    # 3) 当前构建系统命名空间字段
    if system == "uv":
        if "manifest" in build:
            _set_bs("uv", "manifest", _store_path(pm, build["manifest"]),
                    "build.manifest")
        for flag in _UV_FLAGS:
            if flag in build:
                _set_bs("uv", flag, bool(build[flag]), f"build.{flag}")
    else:  # generic
        if "source_dir" in build:
            _set_bs("generic", "source_dir",
                    _store_path(pm, build["source_dir"]), "build.source_dir")
        if "exec_dir" in build:
            _set_bs("generic", "exec_dir",
                    _store_path(pm, build["exec_dir"]), "build.exec_dir")
        for key in _GENERIC_STR:
            if key in build:
                _set_bs("generic", key, build[key], f"build.{key}")
        if "files" in build:
            _set_bs("generic", "extra_files", list(build["files"]), "build.files")

    # 4) entry：入 bs 命名空间（plugin.entry 优先，其次 build.entry）
    entry = plugin.get("entry", build.get("entry"))
    if entry is not None:
        _set_bs(system, "entry", entry, "entry")
    elif system == "uv" and "manifest" in build:
        # 数据副作用（同 GUI）：选 pyproject.toml 时从 [tool.dghub] 自动填入口
        manifest_abs = pm.to_absolute(pm.get_bs_config("uv").get("manifest", ""))
        if manifest_abs:
            auto = read_tool_dghub_entry(Path(manifest_abs))
            if auto:
                _set_bs("uv", "entry", auto, "entry")
                notices.append(f"已从 [tool.dghub] 自动填充入口: {auto}")

    return applied, notices
