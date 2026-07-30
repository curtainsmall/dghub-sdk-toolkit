"""Build DGHub Plugin Packer as a single-file exe.

Usage:
    python build_exe.py [--version X.Y.Z]
    # or with uv: uv sync && uv run build_exe.py
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

TAG_PREFIX = "v"

_VERSION_PATH = ROOT / "src" / "_version.py"

_SEMVER_RE = re.compile(
    r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Packer exe")
    parser.add_argument(
        "--version", default="", metavar="X.Y.Z",
        help="强制指定构建版本号（SemVer），跳过 git tag 读取",
    )
    return parser.parse_args()


def _get_tag() -> str:
    """获取当前版本 tag。

    CI 环境优先读 CI_VERSION_TAG（精确触发 tag），
    本地回退到 git describe --match "v*"。
    """
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
    """写入版本号到 _version.py。

    优先使用 override（--version 参数）；否则从 tag 提取：
    tag 格式: v1.0.0  →  写入 1.0.0，无 tag 时写入空字符串。
    """
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
    _write_version(args.version)
    try:
        return _build()
    finally:
        _reset_version()


def _build() -> int:
    print("Building DGHub Plugin Packer with PyInstaller...")

    src_dir = ROOT / "src"
    sdk_dir = ROOT.parent / "sdk" / "python"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "DGHubPluginPacker",
        "--distpath", str(ROOT / "bin"),
        "--workpath", str(ROOT / "cache" / "build_tmp"),
        "--specpath", str(ROOT / "cache"),
        "--paths", str(src_dir),
        "--paths", str(sdk_dir),
        "--hidden-import", "app",
        "--hidden-import", "manifest_tab",
        "--hidden-import", "distribute_tab",
        "--hidden-import", "settings_tab",
        "--hidden-import", "log_tab",
        "--hidden-import", "logbus",
        "--hidden-import", "project_manager",
        "--hidden-import", "_version",
        "--hidden-import", "manifest_validator",
        "--hidden-import", "exe_builder",
        "--add-data", f"{sdk_dir / 'dghub_sdk'}{os.pathsep}dghub_sdk",
        str(src_dir / "main.py"),
    ]

    result = subprocess.run(cmd, cwd=ROOT)

    if result.returncode == 0:
        print()
        print("Success! Exe created: bin/DGHubPluginPacker.exe")
        print()
        print("Cleaning up build artifacts...")
        _clean(str(ROOT / "cache"))
    else:
        print()
        print(f"Build failed with error code {result.returncode}")
        return result.returncode

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
