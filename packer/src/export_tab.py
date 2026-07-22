"""Export tab — package plugin directory into distributable archives."""

import os
import threading
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Optional

import customtkinter as ctk


class ExportTab(ctk.CTkFrame):
    """Tab for exporting a plugin directory into an archive (Zip, etc.)."""

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, **kwargs)
        self._plugin_dir: Optional[str] = None
        self._running = False
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # -- output path --
        out_frame = ctk.CTkFrame(self)
        out_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        out_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(out_frame, text="输出路径:").grid(row=0, column=0, padx=5, pady=10)
        self._out_label = ctk.CTkLabel(out_frame, text="自动 (与插件目录同名)",
                                       fg_color=("gray85", "gray25"), corner_radius=4,
                                       anchor="w")
        self._out_label.grid(row=0, column=1, sticky="ew", padx=5, pady=10)
        ctk.CTkButton(out_frame, text="另存为...", width=80,
                      command=self._select_output).grid(row=0, column=2, padx=5, pady=10)

        # -- format --
        fmt_frame = ctk.CTkFrame(self)
        fmt_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(5, 10))
        fmt_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(fmt_frame, text="导出格式:").grid(row=0, column=0, padx=5, pady=10)
        self._format_var = ctk.StringVar(value="Zip")
        self._format_menu = ctk.CTkComboBox(fmt_frame, variable=self._format_var,
                                              values=["Zip"], width=120)
        self._format_menu.grid(row=0, column=1, sticky="w", padx=5, pady=10)

        # -- progress / log --
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        btn_frame = ctk.CTkFrame(log_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=0, sticky="ew", pady=(5, 0))
        ctk.CTkLabel(btn_frame, text="导出日志",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        self._export_btn = ctk.CTkButton(btn_frame, text="导出",
                                         command=self._start_export, width=100)
        self._export_btn.pack(side="right", padx=5)

        self._log = ctk.CTkTextbox(log_frame, wrap="word", font=("Consolas", 11))
        self._log.grid(row=1, column=0, sticky="nsew", pady=5)

    def set_plugin_dir(self, d: str) -> None:
        self._plugin_dir = d

    def _select_output(self) -> None:
        if not self._plugin_dir:
            default_name = "plugin.zip"
        else:
            default_name = os.path.basename(self._plugin_dir) + ".zip"

        f = filedialog.asksaveasfilename(
            title="保存为",
            defaultextension=".zip",
            initialfile=default_name,
            filetypes=[("Zip 文件", "*.zip")],
        )
        if f:
            self._out_label.configure(text=f)

    def _log_line(self, msg: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")
        self.update_idletasks()

    def _start_export(self) -> None:
        if self._running:
            return
        if not self._plugin_dir:
            messagebox.showwarning("警告", "请先选择插件目录")
            return

        plugin_path = Path(self._plugin_dir)
        if not plugin_path.is_dir():
            messagebox.showerror("错误", "插件目录不存在")
            return

        # determine output path
        out_text = self._out_label.cget("text")
        if out_text and out_text != "自动 (与插件目录同名)":
            out_path = Path(out_text)
        else:
            out_path = plugin_path.parent / (plugin_path.name + ".zip")

        self._running = True
        self._export_btn.configure(text="导出中...", state="disabled")
        self._log.delete("1.0", "end")
        self._log_line(f"正在打包: {plugin_path}")
        self._log_line(f"输出: {out_path}")

        include_vendor = (plugin_path / "vendor").is_dir()
        if not include_vendor:
            self._log_line("(vendor/ 目录不存在, 跳过)")
        else:
            self._log_line("(发现 vendor/ 目录, 一并打包)")

        def task() -> None:
            try:
                total_files = 0
                with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for root, _dirs, files in os.walk(plugin_path):
                        rel_root = os.path.relpath(root, plugin_path)
                        if rel_root == ".":
                            rel_root = ""
                        # skip vendor if unchecked
                        if rel_root.startswith("vendor") and not include_vendor:
                            continue
                        # skip __pycache__
                        if "__pycache__" in rel_root:
                            continue
                        for fname in files:
                            if fname.endswith(".pyc"):
                                continue
                            fpath = os.path.join(root, fname)
                            arcname = os.path.join(rel_root, fname)
                            zf.write(fpath, arcname)
                            total_files += 1

                self._log_line(f"\n完成！共打包 {total_files} 个文件")
                self._log_line(f"输出大小: {out_path.stat().st_size / 1024:.1f} KB")
                self._log_line(f"文件: {out_path}")
            except Exception as exc:
                self._log_line(f"\n[错误] 导出失败: {exc}")
            finally:
                self._running = False
                self._export_btn.configure(text="导出", state="normal")

        threading.Thread(target=task, daemon=True).start()
