"""构建编排：两阶段管线（validate → 编译 run → collect → package）。

阶段 1 = compile 编译（按 ``compile_system`` 字段显式单选："" 无 /
"python" / "command"），产出文件；阶段 2 = 统一 build 步骤——收集
Builder 条目（+ 编译产物树）→ 生成 manifest → 打包 → 清理。

BuildContext 由 GUI 组装（app.py），本模块不接触前端。经 ctx.log 汇报。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from backend.builder import BuildError, Builder
from backend.build_control import Canceller
from backend.logbus import Logger
from backend.packaging import package_plugin
from backend.producers import (
    ProducerContext,
    get_producer,
    run_logged,
)
from backend.project_manager import ProjectManager


@dataclass
class BuildContext:
    """校验与构建共用的上下文（app.py 组装）。"""

    plugin_dir: Path
    source_dir: Path
    output_dir: Path
    plugin_name: str
    producer_id: str            # ""（无）/ "python" / "command"
    builder: Builder
    log: Logger
    pm: Optional[ProjectManager] = None
    pypi_index: str = ""
    canceller: Optional[Canceller] = None
    # 编译设置字段（compile_system 相关，由 app.py 从 project.json 提取）
    producer_cfg: dict[str, Any] = field(default_factory=dict)


def validate(ctx: BuildContext) -> list[str]:
    """静态校验：编译必要字段、Builder 必要条目（entry 由编译系统自持）。"""
    errors: list[str] = []
    proc = get_producer(ctx.producer_id)
    if proc is not None:
        errors += proc.validate(ctx.producer_cfg, ctx.source_dir)
    errors += ctx.builder.entry_errors(ctx.source_dir)
    return errors


def fill_builder(ctx: BuildContext) -> Optional[list[str]]:
    """「从编译填充」：probe + deduce 串联，只填空。

    将建议落盘（编译设置字段 / Builder 条目），
    返回已应用的描述列表；无编译返回 None（调用方提示）。
    """
    applied: list[str] = []
    proc = get_producer(ctx.producer_id)
    if proc is None or ctx.pm is None:
        return None

    # 0) 先清空既有 derived（编译产物）条目——它们随编译系统/配置变化，
    #    一律以本次 deduce 结果为准重建；用户条目不受影响
    removed = ctx.builder.remove_derived()
    if removed:
        applied.append(f"已刷新 {removed} 个编译产物条目")

    # 1) probe：编译设置为空时探测项目，建议编译设置（落盘）
    if not ctx.producer_cfg.get("manifest") \
            and not ctx.producer_cfg.get("compile"):
        suggest = proc.probe(ctx.plugin_dir)
        if suggest:
            for key, value in suggest.items():
                ctx.pm.set_field(key, value)
                applied.append(f"{key} = {value}")

    # 2) deduce：建议编译产物条目（只填空——已存在 entry 条目不重复添加）
    items = ctx.builder.items()
    has_entry = any("entry" in it.get("tags", []) for it in items)
    deduced = proc.deduce(ctx.producer_cfg, ctx.plugin_name)
    if deduced and not has_entry:
        for item in deduced:
            if "path" in item:
                ctx.builder.add_file(item["path"], item.get("tags"),
                                     derived=bool(item.get("derived")))
                applied.append(f"添加打包内容: {item['path']}（入口）")
            elif "dir" in item:
                ctx.builder.add_dir(item["dir"], item.get("tags"),
                                    derived=bool(item.get("derived")))
                applied.append(f"添加打包内容: {item['dir']}（编译产物）")

    return applied


def run_build(ctx: BuildContext, manifest_data: dict[str, Any]) -> Optional[Path]:
    """执行两阶段构建并打包，返回产物路径；失败返回 None。

    校验失败（BuildError 语义）时返回 None，错误经 ctx.log 记录；
    收集阶段的缺失/冲突抛 ``BuildError``，由调用方（GUI）处理。
    """
    errors = validate(ctx)
    if errors:
        for msg in errors:
            ctx.log.error(msg)
        return None

    # ---- 阶段 1：compile 编译 ----
    proc = get_producer(ctx.producer_id)
    if proc is not None:
        pctx = ProducerContext(
            plugin_dir=ctx.plugin_dir,
            source_dir=ctx.source_dir,
            output_dir=ctx.output_dir,
            plugin_name=ctx.plugin_name,
            cfg=ctx.producer_cfg,
            log=ctx.log,
            pypi_index=ctx.pypi_index,
            canceller=ctx.canceller,
        )
        if not proc.run(pctx):
            return None

    # ---- 阶段 2：收集 + manifest + 打包 ----
    out_files: list[tuple[Path, str]] = []

    # Python 编译产物树（derived 条目从 .pyi/<name>/ 解析）
    prod_dir = ctx.output_dir / ".pyi" / ctx.plugin_name \
        if ctx.producer_id == "python" else None
    if ctx.producer_id == "python" and not prod_dir.is_dir():
        ctx.log.error(f"未找到打包产物: {prod_dir}")
        return None

    # Builder 条目（arc 保留相对路径）；无实际编译输入时入口缺失不豁免
    out_files += ctx.builder.resolve(
        ctx.source_dir,
        entry_exempt=bool(ctx.producer_cfg.get("compile")
                          or ctx.producer_cfg.get("manifest")),
        prod_dir=prod_dir)

    # manifest：entry = entry 标签条目的 arc（validate 已保证恰好一个）
    entry_item = ctx.builder.entry_item()
    assert entry_item is not None and "path" in entry_item
    entry_arc = entry_item["path"]

    # 入口产物兜底校验：entry 文件可能由编译阶段产出（不在 source_dir），
    # 收集完成后必须实际存在（产物树或打包内容之一提供）
    if entry_arc not in {arc for _, arc in out_files}:
        ctx.log.error(f"入口产物缺失: {entry_arc}"
                      "（无编译时请检查打包内容中的入口文件）")
        return None

    data = dict(manifest_data)
    data["entry"] = entry_arc
    data.pop("homepage", None)

    return package_plugin(ctx, data, out_files,
                          ctx.builder.get_no_zip())
