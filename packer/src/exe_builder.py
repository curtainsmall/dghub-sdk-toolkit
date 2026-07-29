"""Build plugin as standalone .exe via PyInstaller.

Handles both interpreter mode and frozen (Packer exe) mode by delegating to
system Python for the actual PyInstaller invocation.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from vendor_packer import _get_python_exe

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _find_sdk_path() -> str:
    """Return the parent directory that contains dghub_sdk package."""
    if getattr(sys, "frozen", False):
        # dghub_sdk bundled via --add-data → _MEIPASS/dghub_sdk/
        return str(Path(sys._MEIPASS))  # pyright: ignore[reportAny]
    else:
        this = Path(__file__).resolve().parent
        return str(this.parent.parent / "sdk" / "python")


def _read_entry(plugin_dir: Path) -> str:
    """Read manifest.json, return entry filename (default 'main.py')."""
    manifest_path = plugin_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            entry = data.get("entry", "main.py")
            if entry:
                return entry
        except (json.JSONDecodeError, OSError):
            pass
    return "main.py"


def _log(msg: str, cb: Optional[Callable[[str], None]]) -> None:
    if cb:
        cb(msg)


def _check_pyinstaller(py_exe: list[str],
                       cb: Optional[Callable[[str], None]]) -> bool:
    """Verify PyInstaller is available before starting the build.

    Runs ``python -m PyInstaller --version``. Returns True on success,
    otherwise logs a clear, actionable message and returns False.
    """
    try:
        result = subprocess.run(
            py_exe + ["-m", "PyInstaller", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=_NO_WINDOW,
        )
    except FileNotFoundError:
        _log("[错误] 未找到 Python 解释器，无法调用 PyInstaller", cb)
        return False
    except Exception as exc:
        _log(f"[错误] 检测 PyInstaller 失败: {exc}", cb)
        return False
    if result.returncode != 0:
        _log("[错误] 未检测到 PyInstaller，请在构建环境执行 "
             "pip install pyinstaller", cb)
        return False
    _log(f"  PyInstaller 版本: {result.stdout.strip()}", cb)
    return True


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def build_plugin_exe(
    plugin_dir: str,
    include_dghub_sdk: bool = True,
    log_callback: Optional[Callable[[str], None]] = None,
    output_dir: str = "",
    source_dir: str = "",
    entry: str = "",
) -> bool:
    """Build a self-contained .exe from a DGHub plugin directory.

    Args:
        plugin_dir: Absolute path to plugin root (where .dghub-sdk lives).
        source_dir: Absolute path to source code root (defaults to plugin_dir).
        include_dghub_sdk: Whether to bundle dghub_sdk.
        log_callback: Optional progress callback.
        output_dir: Output directory for the exe.
        entry: 入口文件（相对 source_dir）；缺省时回退读插件根 manifest.json。

    Returns:
        True on success.
    """
    pdir = Path(plugin_dir).resolve()
    sdir = Path(source_dir).resolve() if source_dir else pdir
    if not pdir.is_dir():
        _log(f"[错误] 插件目录不存在: {pdir}", log_callback)
        return False

    if not entry:
        entry = _read_entry(pdir)
    entry_path = sdir / entry
    if not entry_path.is_file():
        _log(f"[错误] 入口文件不存在: {entry_path}", log_callback)
        return False

    out_dir = Path(output_dir).resolve() if output_dir else pdir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    vendor_dir = sdir / "vendor"
    exe_name = pdir.name
    exe_output = out_dir / f"{exe_name}.exe"
    cache_dir = out_dir / "cache"

    _log(f"[开始] 打包插件 exe: {pdir}", log_callback)
    _log(f"  入口: {entry}", log_callback)

    # ---- build PyInstaller command ----
    py_exe = _get_python_exe()
    if not _check_pyinstaller(py_exe, log_callback):
        return False
    cmd = py_exe + [
        "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", exe_name,
        "--distpath", str(out_dir),
        "--workpath", str(cache_dir / "pyi_build"),
        "--specpath", str(cache_dir),
    ]

    # SDK path
    if include_dghub_sdk:
        sdk_path = _find_sdk_path()
        cmd += ["--paths", sdk_path]
        cmd += ["--hidden-import", "dghub_sdk"]
        cmd += ["--hidden-import", "dghub_sdk.agent"]
        cmd += ["--hidden-import", "dghub_sdk.codec"]
        cmd += ["--hidden-import", "dghub_sdk.enums"]
        _log(f"  dghub_sdk 路径: {sdk_path}", log_callback)

    # vendor path (if exists and not empty)
    if vendor_dir.is_dir() and any(vendor_dir.iterdir()):
        cmd += ["--paths", str(vendor_dir)]
        _log(f"  vendor 路径: {vendor_dir}", log_callback)

    # entry
    cmd.append(str(entry_path))

    _log(f"[运行] PyInstaller ...", log_callback)
    _log(f"  工作目录: {pdir}", log_callback)

    try:
        result = subprocess.run(
            cmd,
            cwd=str(pdir),
            capture_output=True,
            text=True,
            creationflags=_NO_WINDOW,
        )
    except FileNotFoundError:
        _log("[错误] 未找到 Python 解释器，无法运行 PyInstaller", log_callback)
        return False
    except Exception as exc:
        _log(f"[错误] 启动 PyInstaller 失败: {exc}", log_callback)
        return False

    # log PyInstaller output (last few lines on failure)
    if result.returncode != 0:
        _log(f"[错误] PyInstaller 退出码: {result.returncode}", log_callback)
        stderr_tail = result.stderr.strip().splitlines()[-10:]
        for line in stderr_tail:
            _log(f"  {line}", log_callback)
        return False

    if not exe_output.is_file():
        _log(f"[错误] 未生成 exe: {exe_output}", log_callback)
        return False

    size_kb = exe_output.stat().st_size / 1024
    _log(f"[完成] {exe_output} ({size_kb:.1f} KB)", log_callback)
    _log(f"[提示] 将 manifest.json 中 entry 改为 \"{exe_name}.exe\" 即可分发", log_callback)
    return True
