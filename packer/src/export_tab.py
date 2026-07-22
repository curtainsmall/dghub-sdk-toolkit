"""Export tab — package plugin directory into distributable archives."""

import os
import threading
import tkinter as tk
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
        self._file_vars: dict[str, tk.BooleanVar] = {}
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

        # -- file list (expandable) --
        file_frame = ctk.CTkFrame(self)
        file_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(5, 0))
        file_frame.grid_rowconfigure(2, weight=1)
        file_frame.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(file_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(5, 2))
        ctk.CTkLabel(header, text="导出文件列表",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        self._sel_all_btn = ctk.CTkButton(header, text="全选", width=60,
                                          command=self._select_all)
        self._sel_all_btn.pack(side="right", padx=(2, 0))
        self._sel_none_btn = ctk.CTkButton(header, text="取消全选", width=80,
                                           command=self._select_none)
        self._sel_none_btn.pack(side="right", padx=(2, 0))
        self._scan_btn = ctk.CTkButton(header, text="扫描", width=60,
                                       command=self._scan_files)
        self._scan_btn.pack(side="right", padx=(2, 0))

        self._file_count_label = ctk.CTkLabel(file_frame, text="",
                                              font=ctk.CTkFont(size=11))
        self._file_count_label.grid(row=1, column=0, sticky="w", padx=5, pady=(0, 2))

        self._file_scroll = ctk.CTkScrollableFrame(file_frame)
        self._file_scroll.grid(row=2, column=0, sticky="nsew")
        self._file_scroll.grid_columnconfigure(0, weight=1)

        # -- progress / log (fixed height) --
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=5)
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        btn_frame = ctk.CTkFrame(log_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=0, sticky="ew", pady=(5, 0))
        ctk.CTkLabel(btn_frame, text="导出日志",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        self._export_btn = ctk.CTkButton(btn_frame, text="导出",
                                         command=self._start_export, width=100)
        self._export_btn.pack(side="right", padx=5)

        self._log = ctk.CTkTextbox(log_frame, wrap="word", font=("Consolas", 11),
                                   height=100)
        self._log.grid(row=1, column=0, sticky="nsew", pady=5)

    # ------------------------------------------------------------------
    # directory selection
    # ------------------------------------------------------------------

    def set_plugin_dir(self, d: str) -> None:
        self._plugin_dir = d
        self._scan_files()

    def _select_output(self) -> None:
        if not self._plugin_dir:
            default_name = "plugin.zip"
        else:
            default_name = Path(self._plugin_dir).name + ".zip"

        f = filedialog.asksaveasfilename(
            title="保存为",
            defaultextension=".zip",
            initialfile=default_name,
            filetypes=[("Zip 文件", "*.zip")],
        )
        if f:
            self._out_label.configure(text=f)

    # ------------------------------------------------------------------
    # file list management
    # ------------------------------------------------------------------

    def _scan_files(self) -> None:
        """List top-level entries in plugin_dir with checkboxes."""
        if not self._plugin_dir:
            return
        plugin_path = Path(self._plugin_dir)
        if not plugin_path.is_dir():
            return

        # clear
        self._file_vars.clear()
        for child in self._file_scroll.winfo_children():
            child.destroy()

        # collect top-level entries, separate dirs and files
        dirs: list[str] = []
        files: list[str] = []
        for entry in plugin_path.iterdir():
            if entry.is_dir():
                dirs.append(entry.name)
            else:
                files.append(entry.name)
        dirs.sort()
        files.sort()

        row = 0
        for name in dirs + files:
            var = tk.BooleanVar(value=False)
            display = name + "/" if name in dirs else name
            cb = ctk.CTkCheckBox(self._file_scroll, text=display,
                                 variable=var)
            cb.grid(row=row, column=0, sticky="w", padx=5, pady=1)
            self._file_vars[name] = var
            row += 1

        self._file_count_label.configure(
            text=f"共 {len(dirs)} 个目录, {len(files)} 个文件")

    def _select_all(self) -> None:
        for var in self._file_vars.values():
            var.set(True)

    def _select_none(self) -> None:
        for var in self._file_vars.values():
            var.set(False)

    # ------------------------------------------------------------------
    # log
    # ------------------------------------------------------------------

    def _log_line(self, msg: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")
        self.update_idletasks()

    # ------------------------------------------------------------------
    # export
    # ------------------------------------------------------------------

    def _start_export(self) -> None:
        if self._running:
            return
        if not self._plugin_dir:
            if hasattr(self, '_dir_label'):
                self._dir_label.configure(text="请先选择插件目录", text_color="red")
            if hasattr(self, '_dir_path_frame'):
                self._dir_path_frame.configure(border_width=2, border_color="red")
            return

        plugin_path = Path(self._plugin_dir)
        if not plugin_path.is_dir():
            if hasattr(self, '_dir_label'):
                self._dir_label.configure(text="插件目录不存在", text_color="red")
            if hasattr(self, '_dir_path_frame'):
                self._dir_path_frame.configure(border_width=2, border_color="red")
            return

        # collect checked entries
        checked_set = {rel for rel, var in self._file_vars.items() if var.get()}
        if not checked_set:
            self._log_line("[错误] 请至少勾选一个文件或目录")
            return

        checked_dirs = {name for name in checked_set
                        if (plugin_path / name).is_dir()}
        checked_files = checked_set - checked_dirs

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
        self._log_line(f"勾选: {len(checked_set)} 项"
                     f"（{len(checked_dirs)} 个目录, {len(checked_files)} 个文件）")

        def task() -> None:
            try:
                total_files = 0
                with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for root_str, _dirs, files in os.walk(plugin_path):
                        rel = Path(root_str).relative_to(plugin_path)
                        rel_str = "" if rel == Path(".") else rel.as_posix()
                        for fname in files:
                            arcname_str = (rel / fname).as_posix()
                            src = Path(root_str) / fname
                            # direct file match
                            if arcname_str in checked_files:
                                zf.write(src, arcname_str)
                                total_files += 1
                                continue
                            # inside a checked directory
                            for d in checked_dirs:
                                if rel_str == d or rel_str.startswith(d + "/"):
                                    zf.write(src, arcname_str)
                                    total_files += 1
                                    break

                self._log_line(f"\n完成！共打包 {total_files} 个文件")
                self._log_line(f"输出大小: {out_path.stat().st_size / 1024:.1f} KB")
                self._log_line(f"文件: {out_path}")
            except Exception as exc:
                self._log_line(f"\n[错误] 导出失败: {exc}")
            finally:
                self._running = False
                self._export_btn.configure(text="导出", state="normal")

        threading.Thread(target=task, daemon=True).start()
