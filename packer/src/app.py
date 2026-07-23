"""Main application window."""

from tkinter import filedialog
from typing import Any

import customtkinter as ctk

from manifest_tab import ManifestTab
from dependency_tab import DependencyTab
from export_tab import ExportTab
from settings_tab import SettingsTab


class App(ctk.CTk):
    """DGHub Plugin Packer main window."""

    TITLE = "DGHub Plugin Packer"
    WINDOW_SIZE = "1400x1000"

    def __init__(self) -> None:
        super().__init__()

        self.title(self.TITLE)
        self.geometry(self.WINDOW_SIZE)
        self.minsize(900, 600)

        # -- shared directory bar --
        dir_bar = ctk.CTkFrame(self, fg_color="transparent")
        dir_bar.pack(fill="x", padx=10, pady=(10, 0))
        dir_bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(dir_bar, text="插件目录:",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=(0, 5))

        self._dir_path_frame = ctk.CTkFrame(dir_bar, fg_color=("gray85", "gray25"),
                                             border_width=0, corner_radius=6)
        self._dir_path_frame.grid(row=0, column=1, sticky="ew", padx=5)
        self._dir_path_frame.grid_columnconfigure(0, weight=1)

        self._dir_label = ctk.CTkLabel(self._dir_path_frame, text="未选择",
                                        fg_color="transparent", anchor="w")
        self._dir_label.pack(fill="x", expand=True, padx=8, pady=4)
        ctk.CTkButton(dir_bar, text="选择目录", width=100,
                       command=self._select_shared_dir).grid(row=0, column=2, padx=5)

        # -- tab view --
        self._tab_view = ctk.CTkTabview(self, anchor="nw")
        self._tab_view.pack(fill="both", expand=True, padx=10, pady=10)

        # -- tabs --
        self._manifest_tab = self._tab_view.add("Manifest 编辑")
        self._dep_tab = self._tab_view.add("依赖打包")
        self._export_tab = self._tab_view.add("导出")
        self._settings_tab = self._tab_view.add("设置")

        # -- populate tabs --
        self._manifest_view = ManifestTab(self._manifest_tab)
        self._manifest_view.pack(fill="both", expand=True)

        self._dep_view = DependencyTab(self._dep_tab)
        self._dep_view.pack(fill="both", expand=True)

        self._export_view = ExportTab(self._export_tab)
        self._export_view.pack(fill="both", expand=True)

        self._settings_view = SettingsTab(self._settings_tab)
        self._settings_view.pack(fill="both", expand=True)

        # inject directory path frame into tabs (for red border on error)
        self._manifest_view._dir_path_frame = self._dir_path_frame
        self._dep_view._dir_path_frame = self._dir_path_frame
        self._export_view._dir_path_frame = self._dir_path_frame
        self._manifest_view._dir_label = self._dir_label
        self._dep_view._dir_label = self._dir_label
        self._export_view._dir_label = self._dir_label

    def _select_shared_dir(self) -> None:
        """Select a plugin directory and push it to all tabs."""
        d = filedialog.askdirectory(title="选择插件根目录")
        if not d:
            return
        self._dir_label.configure(text=d, text_color=("gray10", "gray90"))
        self._dir_path_frame.configure(border_width=0)
        self._manifest_view.set_plugin_dir(d)
        self._dep_view.set_plugin_dir(d)
        self._export_view.set_plugin_dir(d)
