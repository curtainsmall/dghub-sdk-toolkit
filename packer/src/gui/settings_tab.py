"""Settings / About tab."""

import webbrowser
from tkinter import messagebox
from typing import Any, Callable, Optional

import customtkinter as ctk

from backend import settings_store

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

# 外观模式选项：显示名 → customtkinter 值（默认深色）
_THEME_CHOICES: list[tuple[str, str]] = [
    ("跟随系统", "system"),
    ("浅色", "light"),
    ("深色", "dark"),
]


class SettingsTab(ctk.CTkFrame):
    """Settings and about page."""

    _DEFAULT_HOST = "localhost"
    _DEFAULT_PORT = "8000"

    def __init__(self, master: Any,
                 on_pypi_index_changed: Optional[Callable[[str], None]] = None,
                 **kwargs: Any) -> None:
        super().__init__(master, **kwargs)
        self._on_pypi_index_changed = on_pypi_index_changed
        self._host_var = ctk.StringVar(value=self._DEFAULT_HOST)
        self._port_var = ctk.StringVar(value=self._DEFAULT_PORT)
        self._build_ui()
        self._load_env()

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

    def get_host(self) -> str:
        return self._host_var.get().strip() or self._DEFAULT_HOST

    def get_port(self) -> str:
        return self._port_var.get().strip() or self._DEFAULT_PORT

    def set_host(self, host: str) -> None:
        self._host_var.set(host)
        self._save_env()

    def set_port(self, port: str) -> None:
        self._port_var.set(port)
        self._save_env()

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
        self._theme_menu = ctk.CTkOptionMenu(
            theme_frame, values=[label for label, _ in _THEME_CHOICES],
            command=self._on_theme_changed)
        self._theme_menu.grid(row=1, column=1, sticky="w", padx=5, pady=10)
        self._theme_menu.set("深色")  # 默认深色
        ctk.set_appearance_mode("dark")

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
            text="打包依赖（uv 下载）时使用的下载源；网络无法访问官方源时"
                 "可切换为国内镜像。",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
            wraplength=600, justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="w",
               padx=10, pady=(0, 10))

        # -- Debug (DGHub host/port) --
        runtime_frame = ctk.CTkFrame(self)
        runtime_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=5)
        row += 1

        ctk.CTkLabel(runtime_frame, text="调试设置",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(runtime_frame, text="主机（DGHUB_HOST）:").grid(
            row=1, column=0, sticky="w", padx=(10, 5), pady=(0, 4))
        ctk.CTkEntry(runtime_frame, textvariable=self._host_var, width=240,
                     ).grid(row=1, column=1, sticky="w", padx=5, pady=(0, 4))
        self._host_var.trace_add("write", lambda *_: self._save_env())

        ctk.CTkLabel(runtime_frame, text="端口（DGHUB_PORT）:").grid(
            row=2, column=0, sticky="w", padx=(10, 5), pady=(0, 4))
        ctk.CTkEntry(runtime_frame, textvariable=self._port_var, width=240,
                     ).grid(row=2, column=1, sticky="w", padx=5, pady=(0, 4))
        self._port_var.trace_add("write", lambda *_: self._save_env())

        ctk.CTkLabel(
            runtime_frame,
            text="Packer 调试插件时注入子进程的主机与端口（插件正式运行时"
                 "由 DGHub 主程序自行注入，无需此处配置）。",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
            wraplength=600, justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="w",
               padx=10, pady=(0, 10))

        # -- Reset defaults --
        reset_frame = ctk.CTkFrame(self)
        reset_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=5)
        row += 1

        ctk.CTkButton(reset_frame, text="恢复默认", width=120,
                      command=self._reset_defaults).grid(
            row=0, column=0, sticky="w", padx=10, pady=10)
        ctk.CTkLabel(
            reset_frame,
            text="外观深色、镜像官方源、主机 localhost、端口 8000。",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
        ).grid(row=0, column=1, sticky="w", padx=(0, 10), pady=10)

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

    def _on_theme_changed(self, label: str) -> None:
        """外观模式选项变化 → 应用对应 customtkinter 值。"""
        value = next((v for l, v in _THEME_CHOICES if l == label), "dark")
        ctk.set_appearance_mode(value)

    def _reset_defaults(self) -> None:
        """恢复默认：外观深色、镜像官方源、主机 localhost、端口 8000。"""
        if not messagebox.askyesno(
                "恢复默认",
                "确定恢复全部默认设置？"):
            return
        self._theme_menu.set("深色")
        ctk.set_appearance_mode("dark")
        self._pypi_menu.set(next(iter(PYPI_INDEX_PRESETS)))
        if self._on_pypi_index_changed:
            self._on_pypi_index_changed("")
        self._host_var.set(self._DEFAULT_HOST)
        self._port_var.set(self._DEFAULT_PORT)
        self._save_env()

    def _pypi_changed(self, _label: str) -> None:
        """镜像源选项变化时通知外部（实时保存）。"""
        if self._on_pypi_index_changed:
            self._on_pypi_index_changed(self.get_pypi_index())

    def _load_env(self) -> None:
        saved = settings_store.get_state("debug_env", {})
        if isinstance(saved, dict):
            if saved.get("host") and saved["host"] != "localhost":
                self._host_var.set(saved["host"])
            if saved.get("port") and saved["port"] != "8000":
                self._port_var.set(saved["port"])

    def _save_env(self) -> None:
        settings_store.save_state_key("debug_env", {
            "host": self._host_var.get().strip(),
            "port": self._port_var.get().strip(),
        })
