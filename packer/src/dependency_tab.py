"""Dependencies tab — declare packages to vendor at build time."""

import json
from pathlib import Path
from typing import Any, Optional

import customtkinter as ctk

from project_manager import ProjectManager


class DependencyTab(ctk.CTkFrame):
    """Tab for declaring plugin dependencies.

    No live packing — packages are only vendored during the build pipeline.
    Changes auto-save to `.dghub-sdk/deps.json`.
    """

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, **kwargs)
        self._pm: Optional[ProjectManager] = None
        self._pkgs: list[str] = []
        self._build_ui()
        self._set_enabled(False)

    def _set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for w in self._controls:
            try:
                w.configure(state=state)
            except Exception:
                pass

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # -- header --
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(header, text="声明依赖",
                     font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 10))

        self._pkg_entry = ctk.CTkEntry(header,
                                        placeholder_text="输入包名后点击添加...")
        self._pkg_entry.grid(row=0, column=1, sticky="ew", padx=5)
        self._pkg_entry.bind("<Return>", lambda _: self._add_pkg())

        self._add_btn = ctk.CTkButton(header, text="添加", width=60,
                                      command=self._add_pkg)
        self._add_btn.grid(row=0, column=2, padx=(5, 0))

        self._controls: list[ctk.CTkBaseClass] = []
        self._controls.extend([self._pkg_entry, self._add_btn])

        # -- hint --
        hint_frame = ctk.CTkFrame(self, fg_color="transparent")
        hint_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        ctk.CTkLabel(hint_frame,
                     text="dghub-sdk 会自动包含。DGHub 基础依赖（websockets）和 Python 标准库无需声明，构建时自动跳过。",
                     font=ctk.CTkFont(size=11), text_color="gray",
                     wraplength=600, justify="left").pack(anchor="w")

        # -- package list --
        self._list_frame = ctk.CTkScrollableFrame(self)
        self._list_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        self._list_frame.grid_columnconfigure(0, weight=1)

        self._controls.append(self._list_frame)

    # ------------------------------------------------------------------
    # package management
    # ------------------------------------------------------------------

    def _add_pkg(self) -> None:
        raw = self._pkg_entry.get().strip()
        if not raw:
            return
        # Normalize: replace dash with underscore for Python imports
        name = raw.strip().lower().replace(" ", "_").replace("-", "_")
        if name in self._pkgs or name == "dghub_sdk":
            return
        self._pkgs.append(name)
        self._pkg_entry.delete(0, "end")
        self._refresh_list()
        self._auto_save()

    def _remove_pkg(self, idx: int) -> None:
        if 0 <= idx < len(self._pkgs):
            self._pkgs.pop(idx)
            self._refresh_list()
            self._auto_save()

    def _refresh_list(self) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()

        # Always show dghub-sdk first (immutable)
        self._add_row("dghub_sdk", immutable=True)

        for i, pkg in enumerate(self._pkgs):
            self._add_row(pkg, idx=i)

        if not self._pkgs:
            self._list_frame.grid_rowconfigure(0, weight=1)
        else:
            self._list_frame.grid_rowconfigure(len(self._pkgs), weight=1)

    def _add_row(self, name: str, immutable: bool = False,
                 idx: int = -1) -> None:
        row = ctk.CTkFrame(self._list_frame, fg_color="transparent")
        row.pack(fill="x", padx=2, pady=1)
        row.grid_columnconfigure(0, weight=1)

        label = ctk.CTkLabel(row, text=name, anchor="w")
        label.pack(side="left", fill="x", expand=True)
        self._controls.append(label)

        if immutable:
            ctk.CTkLabel(row, text="✔ 始终包含",
                         text_color="green",
                         font=ctk.CTkFont(size=11)).pack(side="right", padx=(5, 0))
        else:
            del_btn = ctk.CTkButton(row, text="×", width=24, height=22,
                                    fg_color="transparent",
                                    hover_color="#FF4444",
                                    font=ctk.CTkFont(size=14),
                                    command=lambda i=idx: self._remove_pkg(i))
            del_btn.pack(side="right")
            self._controls.append(del_btn)

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------

    def set_plugin_dir(self, d: str, pm: Optional[ProjectManager] = None) -> None:
        if pm:
            self._pm = pm
        self._set_enabled(True)
        if self._pm:
            self._pkgs = self._pm.read_deps()
            self._refresh_list()

    def _auto_save(self) -> None:
        if not self._pm:
            return
        self._pm.write_deps(self._pkgs)

    def get_packages(self) -> list[str]:
        """Return declared packages, including dghub-sdk."""
        return list(self._pkgs)
