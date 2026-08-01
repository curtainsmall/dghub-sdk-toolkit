# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 构建配方：onedir 单 GUI exe（纯 GUI 工具，CLI 已移除）。

产出文件夹 `dghub-sdk-packer/`：`dgpacker-gui.exe`（windowed）+ `_internal/`
（Python 运行时、后端、GUI 只存一份）。由 `build.py` 调用；版本号经
`src/backend/_version.py`（构建期生成）注入。
"""

from pathlib import Path

ROOT = Path(SPECPATH)                     # packer/
SRC = ROOT / "src"
SDK = ROOT.parent / "sdk" / "python"

# 各层 hidden-import（包结构下仍显式列出以降低漏收风险）
_BACKEND = [
    "backend.project_manager", "backend.producers", "backend.builder",
    "backend.pipeline", "backend.exe_builder", "backend.packaging",
    "backend.build_control", "backend.logbus", "backend.manifest_validator",
    "backend.settings_store", "backend.winflags", "backend._version",
]
_GUI = [
    "gui.app", "gui.manifest_tab", "gui.producer_tab", "gui.distribute_tab",
    "gui.settings_tab", "gui.log_tab", "gui.widgets",
]

# SDK 作为数据随包（exe_builder._find_sdk_path 在冻结态读 _MEIPASS/dghub_sdk）
_DATAS = [(str(SDK / "dghub_sdk"), "dghub_sdk")]
_PATHEX = [str(SRC), str(SDK)]

a_gui = Analysis(
    [str(SRC / "gui" / "main.py")],
    pathex=_PATHEX,
    binaries=[],
    datas=_DATAS,
    hiddenimports=_BACKEND + _GUI,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz_gui = PYZ(a_gui.pure)
exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name="dgpacker-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,               # windowed GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe_gui,
    a_gui.binaries,
    a_gui.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="dghub-sdk-packer",
)
