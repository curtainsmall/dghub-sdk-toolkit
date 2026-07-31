"""插件打包：生成产物 manifest.json、写 zip / 文件夹、清理中间产物。

从 GUI 的 app._run_build 抽出，供 GUI 与 CLI 共用（纯逻辑，经 Logger 汇报）。
"""

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from backend.build_systems import BuildContext, BuildSystemSupport


def cleanup_intermediates(output_dir: Path, plugin_name: str) -> None:
    """删除输出目录内的构建中间产物（vendor / cache / 中间 exe）。"""
    temp_vendor = output_dir / "vendor"
    if temp_vendor.is_dir():
        shutil.rmtree(temp_vendor, ignore_errors=True)
    cache_dir = output_dir / "cache"
    if cache_dir.is_dir():
        shutil.rmtree(cache_dir, ignore_errors=True)
    exe_file = output_dir / f"{plugin_name}.exe"
    if exe_file.is_file():
        try:
            exe_file.unlink()
        except OSError:
            pass


def package_plugin(ctx: BuildContext, bs: BuildSystemSupport,
                   manifest_data: dict[str, Any], target: str) -> Path:
    """收集产物并按 target（zip / folder）打包，返回产物路径。

    产物 manifest 的 entry 由构建系统决定（如 exe 模式为 `<名>.exe`）；
    `collect_output` 的存在性校验与 glob 求值在 pre-build 之后执行，
    缺失/冲突时抛 ``BuildError``。打包后清理输出目录内的中间产物。
    """
    data = dict(manifest_data)
    data["entry"] = bs.manifest_entry(ctx)
    data.pop("homepage", None)
    manifest_json = json.dumps(data, ensure_ascii=False, indent=2)

    # 收集产物清单（可能抛 BuildError：缺失文件 / 同名冲突）
    out_files = bs.collect_output(ctx)

    if target == "folder":
        folder_dir = ctx.output_dir / ctx.plugin_name
        folder_dir.mkdir(parents=True, exist_ok=True)
        (folder_dir / "manifest.json").write_text(
            manifest_json, encoding="utf-8")
        for src, arc in out_files:
            dst = folder_dir / arc
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src, dst)
            except Exception as exc:
                ctx.log.warning(f"复制文件失败: {exc}")
        ctx.log.success(f"文件夹已发布: {folder_dir}")
        artifact = folder_dir
    else:  # zip（默认）
        zip_path = ctx.output_dir / f"{ctx.plugin_name}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", manifest_json)
            for src, arc in out_files:
                zf.write(src, arc)
        size_kb = zip_path.stat().st_size / 1024
        ctx.log.success(f"打包完成: {zip_path} ({size_kb:.1f} KB)")
        artifact = zip_path

    cleanup_intermediates(ctx.output_dir, ctx.plugin_name)
    return artifact
