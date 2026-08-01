"""Settings / About tab."""

import webbrowser
from typing import Any, Callable, Optional

import customtkinter as ctk

try:
    from backend._version import __version__ as APP_VERSION
except ImportError:
    # 开发模式：backend/_version.py 仅在构建期生成
    APP_VERSION = "dev"
GITHUB_URL = "https://github.com/curtainsmall/dghub-sdk-toolkit"
DGHUB_URL = "http://dghub.top/"

# PyPI 镜像源预设：显示名 → index URL（空 = 跟随 uv 默认，即官方源）
PYPI_INDEX_PRESETS: dict[str, str] = {
    "官方 (pypi.org)": "",
    "清华 (tuna)": "https://pypi.tuna.tsinghua.edu.cn/simple",
    "阿里云 (aliyun)": "https://mirrors.aliyun.com/pypi/simple",
    "中科大 (ustc)": "https://mirrors.ustc.edu.cn/pypi/simple",
}


class SettingsTab(ctk.CTkFrame):
    """Settings and about page."""

    def __init__(self, master: Any,
                 on_pypi_index_changed: Optional[Callable[[str], None]] = None,
                 **kwargs: Any) -> None:
        super().__init__(master, **kwargs)
        self._on_pypi_index_changed = on_pypi_index_changed
        self._build_ui()

    # -- public API ---------------------------------------------------

    def get_pypi_index(self) -> str:
        """当前生效的镜像源 URL（空 = 官方）。"""
        label = self._pypi_menu.get()
        return PYPI_INDEX_PRESETS.get(label, "")

    def set_pypi_index(self, url: str) -> None:
        """按 URL 恢复下拉选项（未知 URL 回退官方）。"""
        for label, preset_url in PYPI_INDEX_PRESETS.items():
            if preset_url == url:
                self._pypi_menu.set(label)
                return
        self._pypi_menu.set(next(iter(PYPI_INDEX_PRESETS)))

    # -- UI -----------------------------------------------------------

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        row = 0

        # -- App Info --
        info_frame = ctk.CTkFrame(self)
        info_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=(10, 5))
        info_frame.grid_columnconfigure(1, weight=1)
        row += 1

        ctk.CTkLabel(info_frame, text="应用信息",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 5))

        labels = [
            ("应用名称", "DGHub SDK Toolkit — Packer"),
            ("版本", APP_VERSION),
        ]
        for i, (k, v) in enumerate(labels, 1):
            ctk.CTkLabel(info_frame, text=f"{k}:",
                         font=ctk.CTkFont(size=13)).grid(
                row=i, column=0, sticky="w", padx=(10, 5), pady=3)
            ctk.CTkLabel(info_frame, text=v,
                         font=ctk.CTkFont(size=13), text_color=("gray20", "gray80")).grid(
                row=i, column=1, sticky="w", padx=5, pady=3)

        # -- Links --
        link_frame = ctk.CTkFrame(self)
        link_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=5)
        link_frame.grid_columnconfigure(1, weight=1)
        row += 1

        ctk.CTkLabel(link_frame, text="相关链接",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 5))

        ctk.CTkButton(link_frame, text="🌐 GitHub 仓库",
                      command=lambda: webbrowser.open(GITHUB_URL),
                      width=200).grid(row=1, column=0, padx=10, pady=5, sticky="w")
        ctk.CTkButton(link_frame, text="🌐 DGHub 官网",
                      command=lambda: webbrowser.open(DGHUB_URL),
                      width=200).grid(row=2, column=0, padx=10, pady=5, sticky="w")

        # -- Theme --
        theme_frame = ctk.CTkFrame(self)
        theme_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=5)
        row += 1

        ctk.CTkLabel(theme_frame, text="主题设置",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(theme_frame, text="外观模式:").grid(
            row=1, column=0, sticky="w", padx=(10, 5), pady=10)
        theme_menu = ctk.CTkOptionMenu(
            theme_frame, values=["system", "light", "dark"],
            command=ctk.set_appearance_mode)
        theme_menu.grid(row=1, column=1, sticky="w", padx=5, pady=10)
        theme_menu.set("system")

        # -- Build (PyPI index) --
        build_frame = ctk.CTkFrame(self)
        build_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=5)
        row += 1

        ctk.CTkLabel(build_frame, text="构建设置",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(build_frame, text="PyPI 镜像源:").grid(
            row=1, column=0, sticky="w", padx=(10, 5), pady=(0, 4))
        self._pypi_menu = ctk.CTkOptionMenu(
            build_frame, values=list(PYPI_INDEX_PRESETS), width=220,
            command=self._pypi_changed)
        self._pypi_menu.grid(row=1, column=1, sticky="w", padx=5, pady=(0, 4))
        self._pypi_menu.set(next(iter(PYPI_INDEX_PRESETS)))

        ctk.CTkLabel(
            build_frame,
            text="打包依赖到 vendor/ 时使用的下载源；网络无法访问官方源时"
                 "可切换为国内镜像。",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
            wraplength=600, justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="w",
               padx=10, pady=(0, 10))

        # -- License --
        license_frame = ctk.CTkFrame(self)
        license_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=5)
        row += 1

        ctk.CTkLabel(license_frame, text="开源协议",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 2))
        ctk.CTkLabel(
            license_frame,
            text="AGPLv3 — 本项目基于 GNU Affero General Public License v3 开源。",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
            wraplength=600, justify="left",
        ).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 10))

        # push remaining space
        self.grid_rowconfigure(row, weight=1)

    def _pypi_changed(self, _label: str) -> None:
        """镜像源选项变化时通知外部（实时保存）。"""
        if self._on_pypi_index_changed:
            self._on_pypi_index_changed(self.get_pypi_index())
