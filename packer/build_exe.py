"""Build DGHub Plugin Packer as a single-file exe.

Usage:
    python build_exe.py
    # or after pip install -r requirements.txt
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

TAG_PREFIX = "v"


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


def _write_version() -> None:
    """从 tag 提取版本号写入 _version.py。

    tag 格式: v1.0.0  →  写入 1.0.0
    无 tag 时写入空字符串。
    """
    tag = _get_tag()
    version = tag[len(TAG_PREFIX):] if tag.startswith(TAG_PREFIX) else ""
    version_path = ROOT / "src" / "_version.py"
    version_path.write_text(
        f'"""Auto-generated version. Do not edit."""\n__version__ = "{version}"\n',
        encoding="utf-8",
    )
    print(f"Version: {version or '(no version)'}")


def main() -> int:
    _write_version()
    print("Building DGHub Plugin Packer with PyInstaller...")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "DGHubPluginPacker",
        "--distpath", str(ROOT / "bin"),
        "--workpath", str(ROOT / "cache" / "build_tmp"),
        "--specpath", str(ROOT / "cache"),
        str(ROOT / "src" / "main.py"),
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
