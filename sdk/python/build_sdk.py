"""Build DGHub SDK wheel/sdist from git tag.

Usage:
    python build_sdk.py
    # CI 会自动传入 CI_VERSION_TAG 环境变量

构建流程：
  1. 读取 v* tag 提取版本号
  2. 替换 pyproject.toml 中的占位版本
  3. python -m build 生成 wheel + sdist
  4. 恢复 pyproject.toml 占位版本
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYPROJECT = ROOT / "pyproject.toml"
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


def _patch_version(version: str) -> None:
    """将 pyproject.toml 中 version = "0.0.0" 替换为真实版本。"""
    content = PYPROJECT.read_text(encoding="utf-8")
    content = re.sub(
        r'^version = "0\.0\.0"',
        f'version = "{version}"',
        content, count=1,
    )
    PYPROJECT.write_text(content, encoding="utf-8")
    print(f"  Patched pyproject.toml → version = {version}")


def _restore_version() -> None:
    """构建后恢复 pyproject.toml 为占位版本。"""
    content = PYPROJECT.read_text(encoding="utf-8")
    content = re.sub(
        r'^version = "[^"]+"',
        'version = "0.0.0"',
        content, count=1,
    )
    PYPROJECT.write_text(content, encoding="utf-8")
    print("  Restored pyproject.toml → version = 0.0.0")


def _build() -> int:
    print("Building SDK wheel & sdist...")
    result = subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(ROOT / "dist")],
        cwd=ROOT,
    )
    return result.returncode


def main() -> int:
    tag = _get_tag()
    if tag.startswith(TAG_PREFIX):
        version = tag[len(TAG_PREFIX):]
    else:
        version = "0.0.0-dev"
        print(f"Warning: no {TAG_PREFIX}* tag found, using {version}")

    print(f"SDK Version: {version}")
    _patch_version(version)
    try:
        ret = _build()
    finally:
        _restore_version()

    if ret == 0:
        print()
        print("Success! SDK package created in sdk/python/dist/")
        print()
    return ret


if __name__ == "__main__":
    sys.exit(main())
