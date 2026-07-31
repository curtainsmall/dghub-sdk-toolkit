"""DGHub Plugin Packer — CLI 入口（console）。

用法：
    python -m cli.main <子命令> ...        # 从 packer/src 运行
    # 或 PyInstaller 构建后：DGHubPluginPackerCLI.exe build ...（console，stdout 可见）
"""

from pathlib import Path
import sys

# 确保 packer/src 在 sys.path 上，使 backend/cli 作为顶层包可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(argv=None) -> int:
    from cli.cli import dispatch
    return dispatch(argv)


if __name__ == "__main__":
    sys.exit(main())
