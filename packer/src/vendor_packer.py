"""Vendor dependency packing logic.

Supports two methods:
  1. Copy from local site-packages (fastest).
  2. pip download + extract (works without pre-installed deps).
"""

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
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
    name = package_name.strip().lower()
    return name in DGHUB_BASE_DEPS


def _is_stdlib(package_name: str) -> bool:
    """Return True if the package is part of Python's standard library."""
    import importlib.util
    spec = importlib.util.find_spec(package_name)
    return spec is not None and (
        "site-packages" not in (spec.origin or "")
        and "dist-packages" not in (spec.origin or "")
    )


def _should_skip(package_name: str) -> Optional[str]:
    """Return a skip reason if the package should be skipped, else None."""
    name = package_name.strip().lower()
    if name in DGHUB_BASE_DEPS:
        return "DGHub 基础依赖"
    if _is_stdlib(package_name):
        return "Python 标准库"
    return None


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

    # frozen (PyInstaller) fallback: query system Python via launcher
    if getattr(sys, "frozen", False):
        py_name = package_name.replace("-", "_").replace(" ", "_")
        # try py launcher first (Windows), then python
        for cmd in [["py", "-3"], ["py"], ["python"], ["python3"]]:
            try:
                result = subprocess.run(
                    cmd + ["-c",
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
# packing methods
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


_NO_WINDOW_FLAG = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _get_python_exe() -> list[str]:
    """Return [python_exe] suitable for subprocess, handles frozen exe."""
    if not getattr(sys, "frozen", False):
        return [sys.executable]
    for cmd in [["py", "-3"], ["py"], ["python"], ["python3"]]:
        try:
            result = subprocess.run(
                cmd + ["-c", "import sys; print(sys.executable)"],
                capture_output=True, text=True, timeout=5,
                creationflags=_NO_WINDOW_FLAG,
            )
            if result.returncode == 0:
                stripped = result.stdout.strip()
                if stripped:
                    return [stripped]
        except Exception:
            continue
    return [sys.executable]  # fallback


def pip_download_package(
    package_name: str,
    vendor_dir: Path,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """Download a package via pip and extract source into vendor/.

    Returns True on success.
    """
    norm = _normalise_name(package_name)
    with tempfile.TemporaryDirectory(prefix="dghub_packer_") as tmp:
        tmp_path = Path(tmp)
        py_exe = _get_python_exe()
        # pip download
        cmd = py_exe + ["-m", "pip", "download",
            "--no-deps",
            "--only-binary", ":all:",
            "-d", str(tmp_path),
            norm,
        ]
        if progress_callback:
            progress_callback(f"[运行] pip download {norm} ...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=120,
                creationflags=_NO_WINDOW_FLAG,
            )
        except subprocess.TimeoutExpired:
            if progress_callback:
                progress_callback(f"[错误] 下载 '{norm}' 超时")
            return False

        if result.returncode != 0:
            # fallback: try source distribution
            if progress_callback:
                progress_callback(f"[重试] binary 失败，尝试 source 分发 ...")
            cmd_src = py_exe + ["-m", "pip", "download",
                "--no-deps",
                "--no-binary", ":all:",
                "-d", str(tmp_path),
                norm,
            ]
            try:
                result = subprocess.run(
                    cmd_src, capture_output=True, text=True, timeout=120,
                    creationflags=_NO_WINDOW_FLAG,
                )
            except subprocess.TimeoutExpired:
                if progress_callback:
                    progress_callback(f"[错误] 下载 '{norm}' 超时")
                return False

            if result.returncode != 0:
                err = result.stderr.strip() or "未知错误"
                if progress_callback:
                    progress_callback(f"[失败] pip download '{norm}' 出错: {err}")
                return False

        # find downloaded file
        files = list(tmp_path.iterdir())
        if not files:
            if progress_callback:
                progress_callback(f"[失败] 未找到下载文件 '{norm}'")
            return False

        downloaded = files[0]
        pkg_dir = vendor_dir / norm.replace("-", "_")

        if downloaded.suffix == ".whl":
            # extract wheel
            with zipfile.ZipFile(downloaded, "r") as zf:
                # find the pure package dir inside the wheel
                top_level = {p.split("/", 1)[0] for p in zf.namelist() if "/" in p}
                zf.extractall(str(tmp_path))
            # move
            src_candidates = []
            for tl in top_level:
                src_path = tmp_path / tl
                if src_path.is_dir() and (src_path / "__init__.py").exists():
                    src_candidates.append(src_path)
            if not src_candidates:
                # try to find any dir that looks like the package
                for item in tmp_path.iterdir():
                    if item.is_dir() and item.name != "__pycache__":
                        src_candidates.append(item)
            if src_candidates:
                src = src_candidates[0]
                if pkg_dir.exists():
                    shutil.rmtree(pkg_dir)
                shutil.copytree(src, pkg_dir,
                                ignore=_ignore_vendor_and_cache)
                if progress_callback:
                    progress_callback(f"[成功] 已下载并解压 '{norm}' → {pkg_dir}")
                return True
            else:
                if progress_callback:
                    progress_callback(f"[失败] 无法在 wheel 中找到包目录 '{norm}'")
                return False

        elif downloaded.suffix == ".gz" and ".tar.gz" in downloaded.name:
            # extract source tarball
            with tarfile.open(downloaded, "r:gz") as tf:
                tf.extractall(str(tmp_path))
            # find the package dir inside
            extracted_dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
            if not extracted_dirs:
                if progress_callback:
                    progress_callback(f"[失败] 解压后未找到目录 '{norm}'")
                return False
            sub_pkg = extracted_dirs[0] / norm.replace("-", "_")
            if sub_pkg.exists() and sub_pkg.is_dir():
                if pkg_dir.exists():
                    shutil.rmtree(pkg_dir)
                shutil.copytree(sub_pkg, pkg_dir,
                                ignore=_ignore_vendor_and_cache)
                if progress_callback:
                    progress_callback(f"[成功] 已下载并解压 '{norm}' → {pkg_dir}")
                return True
            if progress_callback:
                progress_callback(f"[失败] 解压后未找到包目录 '{norm}'")
            return False
        else:
            if progress_callback:
                progress_callback(f"[失败] 不识别的包格式: {downloaded.suffix}")
            return False


def pack_dependencies(
    package_names: list[str],
    vendor_dir: Path,
    method: str = "auto",
    progress_callback: Optional[Callable[[str], None]] = None,
) -> dict[str, bool]:
    """Pack a list of packages into vendor/.

    Args:
        package_names: List of package names.
        vendor_dir: Target vendor/ directory (will be created).
        method: "site-packages" | "pip" | "auto" (try site-packages first).
        progress_callback: Optional callable for log lines.

    Returns:
        Dict mapping package name -> success (bool).
    """
    vendor_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, bool] = {}

    for name in package_names:
        name = name.strip()
        if not name:
            continue

        skip_reason = _should_skip(name)
        if skip_reason:
            if progress_callback:
                progress_callback(
                    f"[跳过] '{name}' 是 {skip_reason}，无需 vendor")
            results[name] = True
            continue

        ok = False
        if method in ("auto", "site-packages"):
            ok = copy_from_site_packages(name, vendor_dir, progress_callback)
        if not ok and method in ("auto", "pip"):
            ok = pip_download_package(name, vendor_dir, progress_callback)
        results[name] = ok

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
