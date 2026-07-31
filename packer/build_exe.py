"""Build DGHub Plugin Packer executables (GUI and/or CLI).

Usage:
    python build_exe.py [--version X.Y.Z] [--gui | --cli | --both]
    # 未指定目标时默认 --both；可与 --version 并存
    # 或 uv: uv run build_exe.py --version 0.4.0 --both
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

TAG_PREFIX = "v"

# _version.py 归属后端（GUI 关于页与 CLI --version 共用），仅构建期生成
_VERSION_PATH = ROOT / "src" / "backend" / "_version.py"

_SEMVER_RE = re.compile(
    r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$"
)

# 各层需显式声明的 hidden-import（包结构下仍列出以降低漏收风险）
_BACKEND_MODULES = [
    "backend.build_systems", "backend.build_control", "backend.exe_builder",
    "backend.logbus", "backend.manifest_validator", "backend.project_manager",
    "backend.packaging", "backend.build_runner", "backend.settings_store",
    "backend.winflags", "backend.input_apply", "backend._version",
]
_GUI_MODULES = [
    "gui.app", "gui.manifest_tab", "gui.distribute_tab", "gui.settings_tab",
    "gui.log_tab", "gui.widgets",
]
_CLI_MODULES = ["cli.cli", "cli.cli_view"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Packer exe(s)")
    parser.add_argument(
        "--version", default="", metavar="X.Y.Z",
        help="强制指定构建版本号（SemVer），跳过 git tag 读取",
    )
    grp = parser.add_argument_group("构建目标（未指定则默认 --both）")
    grp.add_argument("--gui", action="store_true", help="构建 GUI exe")
    grp.add_argument("--cli", action="store_true", help="构建 CLI exe")
    grp.add_argument("--both", action="store_true", help="构建 GUI + CLI（默认）")
    return parser.parse_args()


def _get_tag() -> str:
    """获取当前版本 tag（CI 优先 CI_VERSION_TAG，本地回退 git describe）。"""
    ci_tag = os.environ.get("CI_VERSION_TAG", "")
    if ci_tag:
        return ci_tag
    try:
        return subprocess.check_output(
            ["git", "describe", "--tags", "--match", f"{TAG_PREFIX}*",
             "--abbrev=0"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _write_version(override: str = "") -> None:
    """写入版本号到 backend/_version.py（tag v1.0.0 → 1.0.0）。"""
    if override:
        version = override
    else:
        tag = _get_tag()
        version = tag[len(TAG_PREFIX):] if tag.startswith(TAG_PREFIX) else ""
    _VERSION_PATH.write_text(
        f'"""Auto-generated version. Do not edit."""\n__version__ = "{version}"\n',
        encoding="utf-8",
    )
    print(f"Version: {version or '(no version)'}")


def _reset_version() -> None:
    """构建结束后删除 _version.py，该文件仅在构建期存在。"""
    _VERSION_PATH.unlink(missing_ok=True)


def main() -> int:
    args = _parse_args()
    if args.version and not _SEMVER_RE.match(args.version):
        print(f"Error: invalid SemVer version: {args.version}")
        return 1
    build_gui = args.gui or args.both or not (args.gui or args.cli)
    build_cli = args.cli or args.both or not (args.gui or args.cli)

    _write_version(args.version)
    try:
        if build_gui:
            rc = _build_target("gui")
            if rc != 0:
                return rc
        if build_cli:
            rc = _build_target("cli")
            if rc != 0:
                return rc
    finally:
        _reset_version()
        _clean(str(ROOT / "cache"))
    return 0


def _build_target(target: str) -> int:
    src_dir = ROOT / "src"
    sdk_dir = ROOT.parent / "sdk" / "python"
    add_data = f"{sdk_dir / 'dghub_sdk'}{os.pathsep}dghub_sdk"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--distpath", str(ROOT / "bin"),
        "--workpath", str(ROOT / "cache" / "build_tmp"),
        "--specpath", str(ROOT / "cache"),
        "--paths", str(src_dir),
        "--paths", str(sdk_dir),
        "--add-data", add_data,
    ]
    for mod in _BACKEND_MODULES:
        cmd += ["--hidden-import", mod]

    if target == "gui":
        name = "DGHubPluginPacker"
        cmd += ["--windowed", "--name", name]
        for mod in _GUI_MODULES:
            cmd += ["--hidden-import", mod]
        cmd.append(str(src_dir / "gui" / "main.py"))
    else:  # cli
        name = "DGHubPluginPackerCLI"
        cmd += ["--name", name, "--console",
                "--exclude-module", "customtkinter"]
        for mod in _CLI_MODULES:
            cmd += ["--hidden-import", mod]
        cmd.append(str(src_dir / "cli" / "main.py"))

    print(f"Building {name} with PyInstaller...")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"\nBuild failed ({name}) with error code {result.returncode}")
        return result.returncode
    print(f"Success! Exe created: bin/{name}.exe")
    return 0


def _clean(path: str) -> None:
    p = Path(path)
    if p.is_dir():
        import shutil
        shutil.rmtree(p, ignore_errors=True)
        print(f"  Removed directory: {p.name}")
    elif p.is_file():
        p.unlink(missing_ok=True)
        print(f"  Removed file: {p.name}")


if __name__ == "__main__":
    sys.exit(main())
