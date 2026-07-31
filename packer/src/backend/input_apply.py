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


def apply_input(pm: ProjectManager, entries: dict[str, Any]) -> list[str]:
    """应用输入清单到 `.dghub-sdk/`，返回告警/提示列表。

    映射：plugin.* → manifest（entry 例外，入 bs 命名空间）；build.system →
    当前构建系统；build.* → 对应命名空间；config_schema → manifest。
    """
    notices: list[str] = []
    plugin = entries.get("plugin") or {}
    build = entries.get("build") or {}
    config_schema = entries.get("config_schema")

    project = pm.read_project()

    # 1) 构建系统 + 插件级键
    system = build.get("system", project.get("build_system", "uv"))
    if system not in BUILD_SYSTEMS:
        notices.append(f"未知构建系统 '{system}'，保持原值")
        system = project.get("build_system", "uv")
    project["build_system"] = system
    if "target" in build:
        project["target"] = build["target"]
    if "output_dir" in build:
        project["output_dir"] = _store_path(pm, build["output_dir"])
    pm.write_project(project)

    # 2) manifest 字段（id/name/version/author/description/capabilities/config_schema）
    manifest = pm.read_manifest()
    for key in ("id", "name", "version", "author", "description"):
        if key in plugin:
            manifest[key] = plugin[key]
    if "capabilities" in plugin:
        manifest["capabilities"] = plugin["capabilities"]
    if config_schema is not None:
        manifest["config_schema"] = config_schema
    pm.write_manifest(manifest)

    # 3) 当前构建系统命名空间字段
    if system == "uv":
        if "manifest" in build:
            pm.set_bs_config("uv", "manifest", _store_path(pm, build["manifest"]))
        for flag in _UV_FLAGS:
            if flag in build:
                pm.set_bs_config("uv", flag, bool(build[flag]))
    else:  # generic
        if "source_dir" in build:
            pm.set_bs_config("generic", "source_dir",
                             _store_path(pm, build["source_dir"]))
        if "exec_dir" in build:
            pm.set_bs_config("generic", "exec_dir",
                             _store_path(pm, build["exec_dir"]))
        for key in _GENERIC_STR:
            if key in build:
                pm.set_bs_config("generic", key, build[key])
        if "files" in build:
            pm.set_bs_config("generic", "extra_files", list(build["files"]))

    # 4) entry：入 bs 命名空间（plugin.entry 优先，其次 build.entry）
    entry = plugin.get("entry", build.get("entry"))
    if entry is not None:
        pm.set_bs_config(system, "entry", entry)
    elif system == "uv" and "manifest" in build:
        # 数据副作用（同 GUI）：选 pyproject.toml 时从 [tool.dghub] 自动填入口
        manifest_abs = pm.to_absolute(pm.get_bs_config("uv").get("manifest", ""))
        if manifest_abs:
            auto = read_tool_dghub_entry(Path(manifest_abs))
            if auto:
                pm.set_bs_config("uv", "entry", auto)
                notices.append(f"已从 [tool.dghub] 自动填充入口: {auto}")

    return notices
