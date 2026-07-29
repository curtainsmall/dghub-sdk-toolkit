"""`.dghub-sdk/` project configuration management.

project.json 为唯一配置文件（format_version 1，按构建系统命名空间分组）::

    {
      "format_version": 1,
      "build_system": "uv",         # 当前选中的构建系统（命名空间键即判别符）
      "output_dir": "",              # 插件级：输出目录（相对插件目录；空 = 自动）
      "target": "zip",               # 插件级：发布目标 zip / folder
      "build_systems": {
        "uv":      {"manifest": "", "entry": "main.py",
                    "build_exe": true, "include_sdk": true},
        "generic": {"source_dir": "", "entry": "",
                    "pre_build": "", "exec_dir": "", "extra_files": []}
      }
    }

- 基类字段（所有系统必有）：entry；uv 以 `manifest`（依赖清单文件）
  为项目根锚点，generic 以 `source_dir`（收集目录）为锚点
- 路径（manifest / source_dir / exec_dir / output_dir）存相对插件目录的路径，跨盘符时回退绝对路径
- 未知命名空间在读-改-写时保留，不丢数据
- 旧格式（develop 平铺、feature 分支中间格式）执行破坏性升级：
  直接重置为默认值并落盘、删除旧 deps.json（manifest.json 不受影响）
"""

import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

# 当前支持的配置格式代数（仅破坏性变更时递增）
_SUPPORTED_FORMAT = 1

_MANIFEST_DEFAULTS: dict[str, Any] = {
    "id": "",
    "name": "",
    "version": "",
    "author": "",
    "description": "",
    "sdk": "1",
}

# 各构建系统配置的默认值（entry 为基类字段；每种语言对应一个系统）
# uv（Python）：`manifest` = 依赖清单文件（相对插件目录；空 = 未选，
# 项目根回退插件目录且跳过依赖打包），项目根 = 清单所在目录
# generic：`source_dir` = 收集目录（原始文件选取根）；
# `exec_dir` = pre-build 执行目录（空 = 插件目录）
_BS_DEFAULTS: dict[str, dict[str, Any]] = {
    "uv": {"manifest": "", "entry": "main.py",
           "build_exe": True, "include_sdk": True},
    "generic": {"source_dir": "", "entry": "",
                "pre_build": "", "exec_dir": "", "extra_files": []},
}

# 顶层插件级共享键默认值
_PROJECT_TOP_DEFAULTS: dict[str, Any] = {
    "build_system": "uv",
    "output_dir": "",
    "target": "zip",
}


class UnsupportedFormatError(Exception):
    """project.json 由更新版本的 Packer 创建，当前版本无法读取。"""


class ProjectManager:
    """Manages a `.dghub-sdk/` directory inside the plugin source directory.

    Each tab auto-reads/writes on every change.
    No explicit "save" needed — this is transparent persistence.
    """

    def __init__(self, plugin_dir: str,
                 log: Optional[Callable[[str], None]] = None) -> None:
        self._plugin_dir = Path(plugin_dir)
        self._root = self._plugin_dir / ".dghub-sdk"
        self._log = log

    def _note(self, msg: str) -> None:
        if self._log:
            self._log(msg)

    # ------------------------------------------------------------------
    # 路径存取（存相对插件目录，跨盘符回退绝对）
    # ------------------------------------------------------------------

    def to_relative(self, path: str) -> str:
        """将绝对路径转为相对插件目录的存储形式；跨盘符时保留绝对路径。"""
        if not path:
            return ""
        try:
            rel = os.path.relpath(path, self._plugin_dir)
        except ValueError:
            self._note(f"[提示] 路径与插件目录不同盘符，将存为绝对路径"
                       f"（不可移植）: {path}")
            return Path(path).as_posix()
        return Path(rel).as_posix()

    def to_absolute(self, stored: str) -> str:
        """将存储的（相对/绝对）路径解析为绝对路径；空串返回空串。"""
        if not stored:
            return ""
        p = Path(stored)
        if p.is_absolute():
            return p.as_posix()
        return (self._plugin_dir / p).resolve().as_posix()

    # ------------------------------------------------------------------
    # Manifest (info tab)
    # ------------------------------------------------------------------

    def read_manifest(self) -> dict[str, Any]:
        """Read `.dghub-sdk/manifest.json`, return dict (merged with defaults)."""
        data = dict(_MANIFEST_DEFAULTS)
        path = self._root / "manifest.json"
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                data.update(loaded)
            except (json.JSONDecodeError, OSError):
                pass
        return data

    def write_manifest(self, data: dict[str, Any]) -> None:
        """Write manifest data to `.dghub-sdk/manifest.json`."""
        self._root.mkdir(parents=True, exist_ok=True)
        merged = dict(_MANIFEST_DEFAULTS)
        merged.update(data)
        (self._root / "manifest.json").write_text(
            json.dumps(merged, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Project config（唯一配置文件，含各构建系统命名空间）
    # ------------------------------------------------------------------

    def _load_json(self, name: str) -> Any:
        path = self._root / name
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return None

    def read_project(self) -> dict[str, Any]:
        """读取并归一化 project.json；旧格式执行破坏性升级（重置默认值）。"""
        raw = self._load_json("project.json")
        deps_path = self._root / "deps.json"

        if isinstance(raw, dict) and "format_version" in raw:
            fv = raw["format_version"]
            if isinstance(fv, int) and fv > _SUPPORTED_FORMAT:
                raise UnsupportedFormatError(
                    f"project.json 格式版本为 {fv}，当前仅支持 "
                    f"{_SUPPORTED_FORMAT}：项目由更新版本的 Packer 创建，"
                    "请升级 Packer")
            if "build_systems" in raw:
                return self._fill_defaults(raw)
            # 带版本号但结构不识别（本分支中间格式）→ 破坏性重置

        # 旧格式 / 结构不识别 → 重置为默认值
        had_legacy = (isinstance(raw, dict) and bool(raw)) \
            or deps_path.is_file()
        data = self._fill_defaults({"format_version": _SUPPORTED_FORMAT})
        if had_legacy:
            self._reset_legacy(data, deps_path)
        return data

    def write_project(self, data: dict[str, Any]) -> None:
        """Write project settings to `.dghub-sdk/project.json`."""
        data.setdefault("format_version", _SUPPORTED_FORMAT)
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / "project.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _fill_defaults(raw: dict[str, Any]) -> dict[str, Any]:
        """补全顶层与已知系统的默认键；未知键/未知命名空间原样保留。"""
        data = dict(raw)
        for k, v in _PROJECT_TOP_DEFAULTS.items():
            data.setdefault(k, v)
        systems = dict(data.get("build_systems", {}))
        for bs_id, defaults in _BS_DEFAULTS.items():
            cfg = dict(defaults)
            cfg.update(systems.get(bs_id, {}))
            systems[bs_id] = cfg
        data["build_systems"] = systems
        return data

    def _reset_legacy(self, data: dict[str, Any], deps_path: Path) -> None:
        """旧版配置破坏性升级：重置落盘并删除旧 deps.json。"""
        try:
            self.write_project(data)
            if deps_path.is_file():
                deps_path.unlink()
            self._note("[提示] 检测到旧版配置，发布设置已重置"
                       "（manifest 不受影响），请重新配置")
        except OSError as exc:
            self._note(f"[警告] 配置重置落盘失败（{exc}），将在下次写入时重试")

    # ------------------------------------------------------------------
    # 构建系统命名空间访问接口
    # ------------------------------------------------------------------

    def get_bs_config(self, bs_id: str) -> dict[str, Any]:
        """Return the build-system namespace config, merged with defaults."""
        project = self.read_project()
        cfg = dict(_BS_DEFAULTS.get(bs_id, {}))
        cfg.update(project.get("build_systems", {}).get(bs_id, {}))
        return cfg

    def set_bs_config(self, bs_id: str, key: str, value: Any) -> None:
        """Set one key in a build-system namespace (read-merge-write)."""
        project = self.read_project()
        systems = project.setdefault("build_systems", {})
        cfg = systems.setdefault(bs_id, dict(_BS_DEFAULTS.get(bs_id, {})))
        cfg[key] = value
        self.write_project(project)

    def read_extra_files(self) -> list[dict[str, str]]:
        """Return extra file entries: [{"path"|"pattern", "dest"}]."""
        return list(self.get_bs_config("generic").get("extra_files", []))

    def write_extra_files(self, files: list[dict[str, str]]) -> None:
        """Write extra file entries into the generic namespace."""
        self.set_bs_config("generic", "extra_files", files)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def get_plugin_id(self) -> str:
        return self.read_manifest().get("id", "")


def project_exists(plugin_dir: str) -> bool:
    """Check if `.dghub-sdk/` exists in the given directory."""
    return (Path(plugin_dir) / ".dghub-sdk" / "manifest.json").is_file()
