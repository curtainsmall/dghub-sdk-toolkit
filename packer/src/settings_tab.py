"""Settings / About tab."""

import webbrowser
from typing import Any

import customtkinter as ctk

from _version import __version__ as APP_VERSION
GITHUB_URL = "https://github.com/curtainsmall/dghub-sdk-toolkit"
DGHUB_URL = "http://dghub.top/"


class SettingsTab(ctk.CTkFrame):
    """Settings and about page."""

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, **kwargs)
        self._build_ui()

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
        theme_menu = ctk.CTkComboBox(
            theme_frame, values=["system", "light", "dark"],
            command=ctk.set_appearance_mode)
        theme_menu.grid(row=1, column=1, sticky="w", padx=5, pady=10)
        theme_menu.set("system")

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
