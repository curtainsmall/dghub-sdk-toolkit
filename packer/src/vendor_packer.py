"""Vendor dependency packing logic.

Only method: copy from local site-packages.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# DGHub base dependencies — plugin authors should NOT vendor these
# ---------------------------------------------------------------------------
DGHUB_BASE_DEPS: frozenset = frozenset({
    "websockets",
    "websockets-legacy",
})


def is_dghub_base_dep(package_name: str) -> bool:
    """Return True if the package is provided by DGHub runtime."""
    return package_name.strip().lower() in DGHUB_BASE_DEPS


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _normalise_name(name: str) -> str:
    """Normalise a package name (PEP 503)."""
    return name.strip().lower().replace("_", "-")


def _find_site_packages(package_name: str) -> Optional[Path]:
    """Find the path of an installed package in site-packages."""
    # try importing it
    try:
        import importlib
        mod = importlib.import_module(package_name)
        mod_path = Path(getattr(mod, "__file__", "") or "")
        if mod_path.name == "__init__.py":
            return mod_path.parent
        return mod_path.parent
    except ImportError:
        pass

    # fallback: walk sys.path
    norm = _normalise_name(package_name)
    norm_underscore = norm.replace("-", "_")
    for sp in sys.path:
        sp_path = Path(sp)
        # package as directory
        cand = sp_path / norm_underscore
        if cand.is_dir() and (cand / "__init__.py").exists():
            return cand
        # single-file module
        cand_file = sp_path / f"{norm_underscore}.py"
        if cand_file.exists():
            return cand_file

    # frozen (PyInstaller) fallback: query system Python
    if getattr(sys, "frozen", False):
        # convert dashes to underscores for valid Python import
        py_name = package_name.replace("-", "_").replace(" ", "_")
        for py in ["python", "python3"]:
            try:
                result = subprocess.run(
                    [py, "-c",
                     f"import {py_name}; print({py_name}.__file__)"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                if result.returncode == 0:
                    # take last line (package may print banner on import)
                    lines = result.stdout.strip().splitlines()
                    p = Path(lines[-1].strip()) if lines else None
                    if p:
                        return p.parent if p.name == "__init__.py" else p.parent
            except Exception:
                continue

    return None


def _ignore_vendor_and_cache(dir: str, contents: list[str]) -> set[str]:
    """Ignore __pycache__, *.pyc, and vendor/ to avoid recursive nesting."""
    ignored: set[str] = set()
    for name in contents:
        if name in ("__pycache__", "vendor") or name.endswith(".pyc"):
            ignored.add(name)
    return ignored


# ---------------------------------------------------------------------------
# packing — only from site-packages
# ---------------------------------------------------------------------------


def copy_from_site_packages(
    package_name: str,
    vendor_dir: Path,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """Copy an installed package from site-packages into vendor/.

    Returns True on success.
    """
    src = _find_site_packages(package_name)
    if src is None:
        if progress_callback:
            progress_callback(f"[失败] 未找到已安装的 '{package_name}'，请先 pip install")
        return False

    dst = vendor_dir / src.name
    if dst.exists():
        shutil.rmtree(dst)

    try:
        if src.is_dir():
            shutil.copytree(src, dst, ignore=_ignore_vendor_and_cache)
        else:
            shutil.copy2(src, dst)
        if progress_callback:
            progress_callback(f"[成功] 已复制 '{package_name}' → {dst}")
        return True
    except Exception as exc:
        if progress_callback:
            progress_callback(f"[错误] 复制 '{package_name}' 失败: {exc}")
        return False


def pack_dependencies(
    package_names: list[str],
    vendor_dir: Path,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> dict[str, bool]:
    """Pack a list of packages from site-packages into vendor/.

    Returns dict mapping package name -> success (bool).
    """
    vendor_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, bool] = {}

    for name in package_names:
        name = name.strip()
        if not name:
            continue
        if is_dghub_base_dep(name):
            if progress_callback:
                progress_callback(f"[跳过] '{name}' 是 DGHub 基础依赖，无需 vendor")
            results[name] = True
            continue
        results[name] = copy_from_site_packages(name, vendor_dir, progress_callback)
    return results


def copy_files_to_vendor(
    source_paths: list[str],
    vendor_dir: Path,
    plugin_dir: Path,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> dict[str, bool]:
    """Copy files/folders into vendor/ for non-Python projects.

    Relative paths are resolved against plugin_dir.
    Returns dict mapping each source path -> success (bool).
    """
    vendor_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, bool] = {}

    for src in source_paths:
        src = src.strip()
        if not src:
            continue

        src_path = Path(src)
        if not src_path.is_absolute():
            src_path = plugin_dir / src_path

        if not src_path.exists():
            if progress_callback:
                progress_callback(f"[失败] 路径不存在: {src}")
            results[src] = False
            continue

        dst = vendor_dir / src_path.name

        # ── pre-validation ──────────────────────────────────────
        # reject paths already inside vendor/ to prevent self-nesting
        if vendor_dir in src_path.parents:
            if progress_callback:
                progress_callback(f"[跳过] '{src}' 已在 vendor/ 目录内，跳过以避免自嵌套")
            results[src] = False
            continue

        try:
            if src_path.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src_path, dst,
                                ignore=_ignore_vendor_and_cache)
            else:
                shutil.copy2(src_path, dst)
            if progress_callback:
                progress_callback(f"[成功] 已复制 '{src}' → {dst}")
            results[src] = True
        except Exception as exc:
            if progress_callback:
                progress_callback(f"[错误] 复制 '{src}' 失败: {exc}")
            results[src] = False

    return results
