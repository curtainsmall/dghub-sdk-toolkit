"""pytest 共享夹具：路径注入与 BuildContext 组装。"""

import sys
from pathlib import Path

import pytest

# backend/gui/cli 为 packer/src 下的顶层包，测试按 backend.* 导入后端
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from backend.build_systems import BuildContext  # noqa: E402
from backend.logbus import Logger  # noqa: E402


class StubDistView:
    """发布页视图的最小替身，仅提供 build_systems 消费的 getter。"""

    def __init__(
        self,
        entry: str = "",
        manifest: str = "",
        build_exe: bool = False,
        include_sdk: bool = False,
        pre_build: str = "",
        exec_dir: str = "",
        extra_files: list[dict[str, str]] | None = None,
    ) -> None:
        self.entry = entry
        self.manifest = manifest
        self.build_exe = build_exe
        self.include_sdk = include_sdk
        self.pre_build = pre_build
        self.exec_dir = exec_dir
        self.extra_files = extra_files or []

    def get_entry(self) -> str:
        return self.entry

    def get_manifest(self) -> str:
        return self.manifest

    def get_build_exe(self) -> bool:
        return self.build_exe

    def get_include_sdk(self) -> bool:
        return self.include_sdk

    def get_pre_build(self) -> str:
        return self.pre_build

    def get_exec_dir(self) -> str:
        return self.exec_dir

    def get_extra_files(self) -> list[dict[str, str]]:
        return self.extra_files


@pytest.fixture
def make_ctx(tmp_path: Path):
    """BuildContext 工厂：自动创建插件/源码/输出目录并收集日志。"""

    def _make(dist_view: StubDistView) -> tuple[BuildContext, list[str]]:
        plugin_dir = tmp_path / "plugin"
        source_dir = tmp_path / "source"
        output_dir = tmp_path / "output"
        for d in (plugin_dir, source_dir, output_dir):
            d.mkdir(exist_ok=True)
        logs: list[str] = []
        ctx = BuildContext(
            plugin_dir=plugin_dir,
            source_dir=source_dir,
            output_dir=output_dir,
            plugin_name="testplugin",
            dist_view=dist_view,
            log=Logger(lambda text, level: logs.append(text)),
        )
        return ctx, logs

    return _make
