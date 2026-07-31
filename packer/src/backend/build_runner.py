"""构建编排：串起「构建系统步骤 → 打包」，供 GUI 与 CLI 共用。

不含校验与配置保存（那是各前端职责），从 build_steps 开始。经 ctx.log 汇报。
"""

from pathlib import Path
from typing import Any, Optional

from backend.build_systems import BuildContext, BuildSystemSupport
from backend.packaging import package_plugin


def run_build(ctx: BuildContext, bs: BuildSystemSupport,
              manifest_data: dict[str, Any], target: str) -> Optional[Path]:
    """执行系统构建步骤并打包，返回产物路径；失败返回 None。

    - `bs.build_steps` 失败（含被取消）时返回 None（其内部已 log）。
    - 收集/打包阶段的缺失或冲突以 ``BuildError`` 抛出，交由调用方处理
      （GUI 可据此高亮「构建」页；CLI 打印错误）。
    """
    if not bs.build_steps(ctx):
        return None
    return package_plugin(ctx, bs, manifest_data, target)
