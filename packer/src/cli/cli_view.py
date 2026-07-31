"""CLI 侧的 dist_view 适配器：从 `.dghub-sdk/` 读配置，满足构建内核的 getter 契约。

与 GUI 的 DistributeTab 对等（同一组 getter），但数据来源是 ProjectManager 读出的
project.json，而非交互控件。路径按 GUI 同款语义解析为绝对/相对，供 build_systems 消费。
"""

from pathlib import Path

from backend.project_manager import ProjectManager


class CliDistView:
    """只读 dist_view：从 project.json 的构建系统命名空间产出各 getter。"""

    def __init__(self, pm: ProjectManager, build_system: str) -> None:
        self._pm = pm
        self._bs_id = build_system
        self._cfg = pm.get_bs_config(build_system)

    # -- 构建内核（build_systems / packaging）消费的 getter --------------

    def get_entry(self) -> str:
        """入口文件（相对源码根，存在性由构建系统在 pre-build 后校验）。"""
        return self._cfg.get("entry", "")

    def get_manifest(self) -> str:
        """依赖清单绝对路径（仅 uv 系使用；未选返回空串）。"""
        return self._pm.to_absolute(self._cfg.get("manifest", ""))

    def get_build_exe(self) -> bool:
        return bool(self._cfg.get("build_exe", False))

    def get_include_sdk(self) -> bool:
        return bool(self._cfg.get("include_sdk", False))

    def get_pre_build(self) -> str:
        return self._cfg.get("pre_build", "")

    def get_exec_dir(self) -> str:
        """pre-build 执行目录绝对路径（未设置返回空串，构建时回退插件目录）。"""
        return self._pm.to_absolute(self._cfg.get("exec_dir", ""))

    def get_extra_files(self) -> list[dict[str, str]]:
        """附加文件条目（path/pattern + dest；路径相对源码根，原样返回）。"""
        return list(self._cfg.get("extra_files", []))

    def get_source_dir(self) -> str:
        """源码根绝对路径：uv 为清单所在目录，generic 为收集目录；空则回退插件目录。"""
        if self._bs_id == "generic":
            src = self._pm.to_absolute(self._cfg.get("source_dir", ""))
            return src or self._pm.plugin_dir.as_posix()
        manifest = self._pm.to_absolute(self._cfg.get("manifest", ""))
        if manifest:
            return Path(manifest).parent.as_posix()
        return self._pm.plugin_dir.as_posix()
