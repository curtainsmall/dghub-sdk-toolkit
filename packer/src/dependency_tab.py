"""Dependency vendor-packing tab."""

import os
import shutil
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Optional

import customtkinter as ctk

from .vendor_packer import (
    DGHUB_BASE_DEPS,
    copy_files_to_vendor,
    is_dghub_base_dep,
    pack_dependencies,
)


class DependencyTab(ctk.CTkFrame):
    """Tab for packing third-party dependencies into vendor/."""

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, **kwargs)
        self._plugin_dir: Optional[str] = None
        self._running = False
        self._vendor_files: list[str] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # -- package input --
        input_frame = ctk.CTkFrame(self)
        input_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        input_frame.grid_columnconfigure(1, weight=1)

        # -- language selector --
        lang_row = ctk.CTkFrame(input_frame, fg_color="transparent")
        lang_row.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=(5, 2))
        ctk.CTkLabel(lang_row, text="项目语言:",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        self._lang_var = ctk.StringVar(value="Python")
        self._lang_menu = ctk.CTkComboBox(
            lang_row, values=["Python", "其他"],
            variable=self._lang_var, command=self._on_lang_change, width=120,
        )
        self._lang_menu.pack(side="left", padx=(8, 0))

        # ============ Python mode ============
        self._python_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        self._python_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")

        ctk.CTkLabel(self._python_frame, text="需要 vendor 的包名:",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=5, pady=(10, 2))

        hint = (f"每行一个包名\n"
                f"DGHub 已提供: {', '.join(sorted(DGHUB_BASE_DEPS))}")
        ctk.CTkLabel(self._python_frame, text=hint,
                     font=ctk.CTkFont(size=11), text_color="gray").grid(
            row=1, column=0, columnspan=2, sticky="w", padx=5)

        self._pkg_text = ctk.CTkTextbox(self._python_frame, height=80, width=300)
        self._pkg_text.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        self._pkg_placeholder = "pymem\nvdf"
        self._pkg_placeholder_active = True
        self._pkg_text.insert("1.0", self._pkg_placeholder)
        self._pkg_text.configure(text_color="gray")
        self._pkg_text.bind("<FocusIn>", self._on_pkg_focus_in)
        self._pkg_text.bind("<FocusOut>", self._on_pkg_focus_out)

        # method
        method_frame = ctk.CTkFrame(self._python_frame, fg_color="transparent")
        method_frame.grid(row=2, column=1, sticky="nw", padx=10, pady=5)
        ctk.CTkLabel(method_frame, text="打包方式:").pack(anchor="w")
        self._method_var = ctk.StringVar(value="auto")
        methods = [("自动 (先找本地安装，没有则 pip 下载)", "auto"),
                   ("从 site-packages 复制", "site-packages"),
                   ("从 pip 下载", "pip")]
        for text, val in methods:
            ctk.CTkRadioButton(method_frame, text=text, variable=self._method_var,
                               value=val).pack(anchor="w", pady=2)

        # ============ Others mode ============
        self._others_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        self._others_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self._others_frame.grid_remove()
        self._others_frame.grid_columnconfigure(0, weight=1)
        self._others_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self._others_frame, text="需要 vendor 的文件/文件夹:",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=5, pady=(10, 2))

        self._vendor_list_frame = ctk.CTkScrollableFrame(
            self._others_frame, height=80)
        self._vendor_list_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=2)
        self._vendor_list_frame.grid_columnconfigure(0, weight=1)

        file_btn_frame = ctk.CTkFrame(self._others_frame, fg_color="transparent")
        file_btn_frame.grid(row=2, column=0, sticky="w", padx=5, pady=5)
        ctk.CTkButton(file_btn_frame, text="添加文件", width=100,
                      command=self._add_file).pack(side="left", padx=(0, 5))
        ctk.CTkButton(file_btn_frame, text="添加文件夹", width=100,
                      command=self._add_directory).pack(side="left", padx=5)

        # -- progress log --
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        log_frame.grid_rowconfigure(0, weight=0)
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        btn_frame = ctk.CTkFrame(log_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=0, sticky="ew", pady=(5, 0))
        ctk.CTkLabel(btn_frame, text="打包日志",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        self._start_btn = ctk.CTkButton(btn_frame, text="开始打包",
                                        command=self._start_pack, width=100)
        self._start_btn.pack(side="right", padx=5)
        self._clear_vendor_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(btn_frame, text="打包前清空 vendor/",
                        variable=self._clear_vendor_var).pack(
            side="right", padx=(0, 5))
        self._force_vendor_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(btn_frame, text="始终添加 vendor/ 目录",
                        variable=self._force_vendor_var).pack(side="right", padx=(0, 5))

        self._log = ctk.CTkTextbox(log_frame, wrap="word", font=("Consolas", 11))
        self._log.grid(row=1, column=0, sticky="nsew", pady=5)
        self._log.configure(state="disabled")

    # ------------------------------------------------------------------
    # language switch
    # ------------------------------------------------------------------

    def _on_lang_change(self, lang: str) -> None:
        if lang == "Python":
            self._python_frame.grid()
            self._others_frame.grid_remove()
        else:
            self._python_frame.grid_remove()
            self._others_frame.grid()

    # ------------------------------------------------------------------
    # file / folder picker (Others mode)
    # ------------------------------------------------------------------

    def _add_file(self) -> None:
        files = filedialog.askopenfilenames(title="选择需要 vendor 的文件")
        for f in files:
            if f not in self._vendor_files:
                self._vendor_files.append(f)
        self._refresh_vendor_list()

    def _add_directory(self) -> None:
        d = filedialog.askdirectory(title="选择需要 vendor 的文件夹")
        if d and d not in self._vendor_files:
            self._vendor_files.append(d)
            self._refresh_vendor_list()

    def _remove_vendor_file(self, idx: int) -> None:
        if 0 <= idx < len(self._vendor_files):
            self._vendor_files.pop(idx)
            self._refresh_vendor_list()

    def _refresh_vendor_list(self) -> None:
        for w in self._vendor_list_frame.winfo_children():
            w.destroy()
        if not self._vendor_files:
            ctk.CTkLabel(self._vendor_list_frame, text="(尚未添加任何文件或文件夹)",
                         text_color="gray").pack(pady=10)
            return
        for i, path in enumerate(self._vendor_files):
            row = ctk.CTkFrame(self._vendor_list_frame, fg_color="transparent")
            row.pack(fill="x", padx=2, pady=1)
            ctk.CTkLabel(row, text=path, anchor="w").pack(
                side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="×", width=24, height=22,
                          fg_color="transparent", hover_color="#FF4444",
                          font=ctk.CTkFont(size=14),
                          command=lambda idx=i: self._remove_vendor_file(idx)
                          ).pack(side="right")

    # ------------------------------------------------------------------
    # common
    # ------------------------------------------------------------------

    def set_plugin_dir(self, d: str) -> None:
        self._plugin_dir = d

    def _clear_vendor_if_needed(self) -> None:
        if not self._clear_vendor_var.get():
            return
        vendor_dir = Path(self._plugin_dir) / "vendor"
        if vendor_dir.is_dir():
            shutil.rmtree(vendor_dir)
            self._log_line("已清空 vendor/ 目录")

    def _on_pkg_focus_in(self, event: Any = None) -> None:
        if self._pkg_placeholder_active:
            self._pkg_text.delete("1.0", "end")
            self._pkg_text.configure(text_color=("black", "white"))
            self._pkg_placeholder_active = False

    def _on_pkg_focus_out(self, event: Any = None) -> None:
        content = self._pkg_text.get("1.0", "end").strip()
        if not content:
            self._pkg_text.insert("1.0", self._pkg_placeholder)
            self._pkg_text.configure(text_color="gray")
            self._pkg_placeholder_active = True

    def _log_line(self, msg: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")
        self.update_idletasks()

    def _start_pack(self) -> None:
        if self._running:
            return

        if not self._plugin_dir:
            messagebox.showwarning("警告", "请先选择插件目录")
            return

        self._running = True
        self._start_btn.configure(text="打包中...", state="disabled")
        self._log.delete("1.0", "end")

        lang = self._lang_var.get()
        if lang == "Python":
            self._start_pack_python()
        else:
            self._start_pack_others()

    def _start_pack_python(self) -> None:
        if self._pkg_placeholder_active:
            pkgs: list[str] = []
        else:
            raw = self._pkg_text.get("1.0", "end").strip()
            pkgs = [p.strip() for p in raw.replace(",", "\n").split("\n") if p.strip()]

        # check for base deps
        base_deps = [p for p in pkgs if is_dghub_base_dep(p)]
        if base_deps:
            if not messagebox.askyesno(
                "基础依赖",
                f"以下包是 DGHub 已提供的基础依赖，通常不需要 vendor:\n"
                f"{', '.join(base_deps)}\n\n仍然继续？"
            ):
                self._finish_pack()
                return

        # zero-pack: force create an empty vendor/ if option is checked
        if not pkgs:
            self._handle_zero_pack()
            return

        self._log_line(f"开始打包 {len(pkgs)} 个依赖到 vendor/ ...")

        method = self._method_var.get()
        vendor_dir = Path(self._plugin_dir) / "vendor"

        self._clear_vendor_if_needed()

        def task() -> None:
            results = pack_dependencies(
                pkgs, vendor_dir, method=method,
                progress_callback=self._log_line,
            )
            success = sum(1 for v in results.values() if v)
            total = len(results)
            self._log_line(
                f"\n{'='*40}\n打包完成: {success}/{total} 成功"
            )
            self._finish_pack()

        threading.Thread(target=task, daemon=True).start()

    def _start_pack_others(self) -> None:
        if not self._vendor_files:
            self._handle_zero_pack()
            return

        self._log_line(f"开始复制 {len(self._vendor_files)} 个文件/文件夹到 vendor/ ...")
        vendor_dir = Path(self._plugin_dir) / "vendor"
        plugin_dir = Path(self._plugin_dir)
        files_copy = list(self._vendor_files)

        self._clear_vendor_if_needed()

        def task() -> None:
            results = copy_files_to_vendor(
                files_copy, vendor_dir, plugin_dir,
                progress_callback=self._log_line,
            )
            success = sum(1 for v in results.values() if v)
            total = len(results)
            self._log_line(
                f"\n{'='*40}\n打包完成: {success}/{total} 成功"
            )
            self._finish_pack()

        threading.Thread(target=task, daemon=True).start()

    def _handle_zero_pack(self) -> None:
        if self._force_vendor_var.get():
            (Path(self._plugin_dir) / "vendor").mkdir(exist_ok=True)
            self._log_line("零包模式: 已创建空的 vendor/ 目录")
        else:
            self._log_line("零包模式: 跳过 vendor/ 目录")
        self._log_line(f"\n{'='*40}\n打包完成: 0/0 成功")
        self._finish_pack()

    def _finish_pack(self) -> None:
        self._running = False
        self._start_btn.configure(text="开始打包", state="normal")
