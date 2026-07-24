"""Distribute tab — configure how the plugin is built and packaged."""

from pathlib import Path
from typing import Any, Optional

import customtkinter as ctk

from project_manager import ProjectManager


class DistributeTab(ctk.CTkFrame):
    """Tab for configuring build/publish options for the plugin."""

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, **kwargs)
        self._pm: Optional[ProjectManager] = None
        self._plugin_dir: Optional[str] = None
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
        self.grid_rowconfigure(3, weight=1)

        self._controls: list[ctk.CTkBaseClass] = []

        # -- entry file --
        entry_frame = ctk.CTkFrame(self)
        entry_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        entry_frame.grid_columnconfigure(1, weight=1)

        label_frame = ctk.CTkFrame(entry_frame, fg_color="transparent")
        label_frame.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        ctk.CTkLabel(label_frame, text="入口文件 ",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkLabel(label_frame, text="*", text_color="red",
                     font=ctk.CTkFont(size=14)).pack(side="left")
        self._entry_var = ctk.StringVar(value="main.py")
        self._entry_entry = ctk.CTkEntry(entry_frame, textvariable=self._entry_var)
        self._entry_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=10)
        self._controls.append(self._entry_entry)
        ctk.CTkLabel(entry_frame, text="相对于源码目录",
                     font=ctk.CTkFont(size=11),
                     text_color="gray").grid(row=0, column=2, padx=(5, 10))

        # -- build options --
        opt_frame = ctk.CTkFrame(self)
        opt_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        opt_frame.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(opt_frame, text="构建选项",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))

        self._build_exe_var = ctk.BooleanVar(value=True)
        self._build_exe_cb = ctk.CTkCheckBox(opt_frame, text="构建为独立 exe",
                                              variable=self._build_exe_var,
                                              command=self._on_build_exe_toggle)
        self._build_exe_cb.grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self._controls.append(self._build_exe_cb)

        self._include_sdk_var = ctk.BooleanVar(value=True)
        self._include_sdk_cb = ctk.CTkCheckBox(opt_frame, text="包含 dghub-sdk",
                                                variable=self._include_sdk_var)
        self._include_sdk_cb.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        self._controls.append(self._include_sdk_cb)

        # -- publish target --
        target_frame = ctk.CTkFrame(self)
        target_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        ctk.CTkLabel(target_frame, text="发布目标",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))

        self._target_var = ctk.StringVar(value="zip")
        for text, val in [("文件夹（本地调试）", "folder"),
                          ("zip 包（分发）", "zip")]:
            rb = ctk.CTkRadioButton(target_frame, text=text,
                                    variable=self._target_var, value=val)
            rb.pack(anchor="w", padx=20, pady=2)
            self._controls.append(rb)

        # -- preview (bottom area, expandable) --
        preview_frame = ctk.CTkFrame(self)
        preview_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=(10, 0))
        preview_frame.grid_rowconfigure(1, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(preview_frame, text="输出文件预览",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 5))

        self._preview = ctk.CTkTextbox(preview_frame, wrap="word",
                                       font=("Consolas", 11), state="disabled")
        self._preview.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self._controls.append(self._preview)

    def _on_build_exe_toggle(self) -> None:
        self._refresh_preview()

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------

    def set_plugin_dir(self, d: str, pm: Optional[ProjectManager] = None) -> None:
        if pm:
            self._pm = pm
        self._plugin_dir = d
        self._set_enabled(True)
        if self._pm:
            # Load saved project settings
            project = self._pm.read_project()
            if "entry" in project:
                self._entry_var.set(project["entry"])
            if "build_exe" in project:
                self._build_exe_var.set(project["build_exe"])
            if "include_sdk" in project:
                self._include_sdk_var.set(project["include_sdk"])
            if "target" in project:
                self._target_var.set(project["target"])
        self._refresh_preview()

    def _auto_save(self) -> None:
        if not self._pm:
            return
        # Distribute tab saves settings lazily (not on every keystroke)
        # Call this explicitly when needed

    def save_settings(self) -> None:
        """Save current distribute settings to project config."""
        if not self._pm:
            return
        data = {
            "entry": self._entry_var.get(),
            "build_exe": self._build_exe_var.get(),
            "include_sdk": self._include_sdk_var.get(),
            "target": self._target_var.get(),
        }
        self._pm.write_project(data)

    def refresh_preview(self, output_dir: str = "") -> None:
        """Update the file tree preview. Called from app.py."""
        self._refresh_preview(output_dir)

    def _refresh_preview(self, out_dir: str = "") -> None:
        plugin_name = Path(self._plugin_dir).name if self._plugin_dir else "插件名"
        lines: list[str] = []
        lines.append(f"{'='*30}")
        lines.append(f"输出目录: {out_dir or f'（默认 {plugin_name}_output/）'}")

        if self._build_exe_var.get():
            lines.append(f"  {plugin_name}.exe  ← 构建 exe（entry 自动改为 {plugin_name}.exe）")
        else:
            lines.append(f"  源码将保持 entry = {self._entry_var.get()}")

        target = self._target_var.get()
        if target == "zip":
            lines.append(f"  {plugin_name}.zip  ← 分发包")
        elif target == "folder":
            lines.append(f"  dev/{plugin_name}/")
            lines.append(f"    ├── manifest.json")
            lines.append(f"    ├── {self._entry_var.get()}")
            lines.append(f"    └── vendor/")

        self._preview.configure(state="normal")
        self._preview.delete("1.0", "end")
        self._preview.insert("1.0", "\n".join(lines))
        self._preview.configure(state="disabled")

    # ------------------------------------------------------------------
    # accessors for build pipeline
    # ------------------------------------------------------------------

    def get_entry(self) -> str:
        return self._entry_var.get().strip()

    def get_build_exe(self) -> bool:
        return self._build_exe_var.get()

    def get_include_sdk(self) -> bool:
        return self._include_sdk_var.get()

    def get_target(self) -> str:
        return self._target_var.get()

    def clear_entry_error(self) -> None:
        """Reset entry field border after source dir change."""
        self._entry_entry.configure(border_width=0)
