"""Build DGHub Plugin Packer as a single-file exe.

Usage:
    python build_exe.py
    # or after pip install -r requirements.txt
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _write_version() -> None:
    """Write packer/_version.py from git tag, or leave empty."""
    version_path = ROOT / "src" / "_version.py"
    try:
        tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        version_path.write_text(
            f'"""Auto-generated version. Do not edit."""\n__version__ = "{tag}"\n',
            encoding="utf-8",
        )
        print(f"Version: {tag}")
    except Exception:
        version_path.write_text(
            '"""Auto-generated version. Do not edit."""\n__version__ = ""\n',
            encoding="utf-8",
        )
        print("Version: (no git tag)")


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
