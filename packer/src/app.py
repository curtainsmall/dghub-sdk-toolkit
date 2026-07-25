"""Main application window — cross-tab layout with top/bottom bars."""

import json
import os
import threading
import zipfile
from pathlib import Path
from tkinter import filedialog
from typing import Any, Optional


def _norm(p: str) -> str:
    """Normalize path separators to forward slashes."""
    return Path(p).as_posix()

import customtkinter as ctk

from dependency_tab import DependencyTab
from distribute_tab import DistributeTab
from exe_builder import build_plugin_exe
from log_tab import LogTab
from manifest_tab import ManifestTab
from project_manager import ProjectManager, project_exists
from settings_tab import SettingsTab
from vendor_packer import pack_dependencies, is_dghub_base_dep, _is_stdlib

_STATE_DIR = Path.home() / ".dghub-sdk-packer"
_STATE_DIR.mkdir(parents=True, exist_ok=True)
_STATE_FILE = _STATE_DIR / "state.json"


class App(ctk.CTk):
    """DGHub Plugin Packer main window."""

    TITLE = "DGHub Plugin Packer"
    WINDOW_SIZE = "1400x1000"

    def __init__(self) -> None:
        super().__init__()

        self.title(self.TITLE)
        self.geometry(self.WINDOW_SIZE)
        self.minsize(900, 600)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # -- state --
        self._plugin_dir: Optional[str] = None
        self._source_dir: Optional[str] = None
        self._source_auto = True
        self._output_dir: Optional[str] = None
        self._output_auto = True
        self._pm: Optional[ProjectManager] = None
        self._running = False
        self._build_success = False

        # -- top bar (cross-tab) --
        self._build_top_bar()

        # -- tab view --
        self._tab_view = ctk.CTkTabview(self, anchor="nw")
        self._tab_view.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)

        # -- tabs --
        self._info_tab = self._tab_view.add("信息")
        self._dep_tab = self._tab_view.add("依赖")
        self._dist_tab = self._tab_view.add("发布")
        self._settings_tab = self._tab_view.add("设置")
        self._log_tab = self._tab_view.add("日志")

        # -- populate tabs --
        self._info_view = ManifestTab(self._info_tab)
        self._info_view.pack(fill="both", expand=True)

        self._dep_view = DependencyTab(self._dep_tab)
        self._dep_view.pack(fill="both", expand=True)

        self._dist_view = DistributeTab(self._dist_tab)
        self._dist_view.pack(fill="both", expand=True)

        self._settings_view = SettingsTab(self._settings_tab)
        self._settings_view.pack(fill="both", expand=True)

        self._log_view = LogTab(self._log_tab)
        self._log_view.pack(fill="both", expand=True)

        # -- bottom bar (cross-tab) --
        self._build_bottom_bar()

        # -- auto-load last plugin dir --
        self._auto_open_last_plugin_dir()

    # ------------------------------------------------------------------
    # top bar
    # ------------------------------------------------------------------

    def _build_top_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        bar.grid_columnconfigure(1, weight=1)
    
        BTN_W = 100
        
        # Store buttons for state management
        self._src_btns: list[ctk.CTkBaseClass] = []
        self._out_btns: list[ctk.CTkBaseClass] = []
        
        def _make_dir_row(bar, row, label, text, select_cmd, reset_cmd=None):
            """Helper to build a uniform directory selector row.
            Returns (frame, lbl, [buttons...]).
            """
            ctk.CTkLabel(bar, text=label,
                         font=ctk.CTkFont(weight="bold")).grid(
                row=row, column=0, padx=(0, 5), pady=4, sticky="w")
            frame = ctk.CTkFrame(bar, fg_color=("gray85", "gray25"),
                                 border_width=0, corner_radius=6)
            frame.grid(row=row, column=1, sticky="ew", padx=5, pady=4)
            frame.grid_columnconfigure(0, weight=1)
            lbl = ctk.CTkLabel(frame, text=text, fg_color="transparent",
                               anchor="w")
            lbl.pack(fill="x", expand=True, padx=8, pady=4)
        
            btn_frame = ctk.CTkFrame(bar, fg_color="transparent")
            btn_frame.grid(row=row, column=2, padx=5, pady=4, sticky="w")
            btn = ctk.CTkButton(btn_frame, text="选择目录", width=BTN_W,
                                command=select_cmd)
            btn.pack(side="left")
            btns = [btn]
            if reset_cmd:
                reset_btn = ctk.CTkButton(btn_frame, text="↺", width=28,
                        command=reset_cmd, fg_color="transparent",
                        hover_color=("gray70", "gray40"),
                        font=ctk.CTkFont(size=16))
                reset_btn.pack(side="left", padx=(5, 0))
                btns.append(reset_btn)
            return frame, lbl, btns
        
        # Row 0: 插件目录（始终可用）
        self._dir_path_frame, self._dir_label, _ = _make_dir_row(
            bar, 0, "插件目录:", "未选择", self._select_shared_dir)
        
        # Row 1: 源码目录（初始禁用）
        self._src_path_frame, self._src_label, self._src_btns = _make_dir_row(
            bar, 1, "源码目录:", "", self._select_source_dir,
            reset_cmd=self._reset_source_dir)
        
        # Row 2: 输出目录（初始禁用）
        self._out_path_frame, self._out_label, self._out_btns = _make_dir_row(
            bar, 2, "输出目录:", "", self._select_output_dir,
            reset_cmd=self._reset_output_dir)
        
        # Initially disable source and output rows
        for b in self._src_btns + self._out_btns:
            b.configure(state="disabled")

    # ------------------------------------------------------------------
    # bottom bar
    # ------------------------------------------------------------------

    def _build_bottom_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        bar.grid_columnconfigure(0, weight=1)

        self._build_btn = ctk.CTkButton(
            bar, text="构建", command=self._start_build,
            width=120, height=36, font=ctk.CTkFont(size=14, weight="bold"))
        self._build_btn.pack(side="right", padx=5)

        self._build_status = ctk.CTkLabel(bar, text="",
                                          font=ctk.CTkFont(size=12),
                                          anchor="e")
        self._build_status.pack(side="right", padx=(5, 10))

    # ------------------------------------------------------------------
    # directory selection
    # ------------------------------------------------------------------

    def _select_source_dir(self) -> None:
        d = filedialog.askdirectory(title="选择源码目录")
        if not d:
            return
        self._source_dir = d
        self._source_auto = False
        self._src_label.configure(text=_norm(d), text_color=("gray10", "gray90"))
        self._src_path_frame.configure(border_width=0)
        self._dist_view.clear_entry_error()
        self._clear_tab_highlight("发布")
        self._save_source_dir(d)
        # Ensure output dir auto-color is preserved
        if self._output_auto:
            self._out_label.configure(text_color=("gray60", "gray60"))

    def _reset_source_dir(self) -> None:
        """Reset source dir back to plugin dir (auto mode)."""
        if self._plugin_dir:
            self._source_dir = self._plugin_dir
            self._source_auto = True
            self._src_label.configure(text=_norm(self._plugin_dir),
                                      text_color=("gray60", "gray60"))
            self._src_path_frame.configure(border_width=0)
            self._dist_view.clear_entry_error()
            self._clear_tab_highlight("发布")
            self._save_source_dir("")
            # Ensure output dir auto-color is preserved
            if self._output_auto:
                self._out_label.configure(text_color=("gray60", "gray60"))

    def _select_output_dir(self) -> None:
        d = filedialog.askdirectory(title="选择输出目录")
        if not d:
            return
        self._output_dir = d
        self._out_label.configure(text=_norm(d), text_color=("gray10", "gray90"))
        self._output_auto = False
        self._out_path_frame.configure(border_width=0)
        self._dist_view.refresh_preview(_norm(d))
        self._save_output_dir(_norm(d))
        # Ensure source dir auto-color is preserved
        if self._source_auto:
            self._src_label.configure(text_color=("gray60", "gray60"))

    def _reset_output_dir(self) -> None:
        """Reset output dir to default (source_dir/output)."""
        if self._plugin_dir:
            default_out = _norm(Path(self._plugin_dir) / "output")
            self._output_dir = default_out
            self._out_label.configure(text=default_out, text_color=("gray60", "gray60"))
            self._output_auto = True
            self._out_path_frame.configure(border_width=0)
            self._dist_view.refresh_preview(default_out)
            self._save_output_dir("")
            # Ensure source dir auto-color is preserved
            if self._source_auto:
                self._src_label.configure(text_color=("gray60", "gray60"))

    def _save_output_dir(self, out_dir: str) -> None:
        """Persist output dir setting to project config."""
        if self._pm:
            project = self._pm.read_project()
            project["output_dir"] = out_dir
            self._pm.write_project(project)

    # ------------------------------------------------------------------
    # validation
    # ------------------------------------------------------------------

    def _clear_error_styles(self) -> None:
        """Reset all error states."""
        self._dir_path_frame.configure(border_width=0, border_color="")
        self._dir_label.configure(text_color=("gray10", "gray90"))
        self._src_path_frame.configure(border_width=0, border_color="")
        self._src_label.configure(text_color=("gray10", "gray90"))
        self._out_path_frame.configure(border_width=0, border_color="")
        self._out_label.configure(text_color=("gray10", "gray90"))
        # Reset tab colors
        self._tab_view._segmented_button._buttons_dict["信息"].configure(
            text_color=("gray10", "gray90"))
        self._tab_view._segmented_button._buttons_dict["依赖"].configure(
            text_color=("gray10", "gray90"))
        self._tab_view._segmented_button._buttons_dict["发布"].configure(
            text_color=("gray10", "gray90"))

    def _tab_color(self, name: str, color: str) -> None:
        """Set a tab's title color."""
        try:
            btn = self._tab_view._segmented_button._buttons_dict.get(name)
            if btn:
                btn.configure(text_color=color)
        except Exception:
            pass

    def _highlight_tab(self, tab_name: str) -> None:
        self._tab_color(tab_name, "#FF4444")

    def _clear_tab_highlight(self, tab_name: str) -> None:
        self._tab_color(tab_name, ("gray10", "gray90"))

    def _highlight_field(self, widget: Any) -> None:
        """Apply red border to a CTkEntry."""
        try:
            widget.configure(border_width=2, border_color="#FF4444")
        except Exception:
            pass

    def _validate_info_tab(self) -> bool:
        """Validate 信息 tab fields. Returns True if valid."""
        manifest = self._info_view._build_manifest()
        id_val = manifest.get("id", "")
        name_val = manifest.get("name", "")
        version_val = manifest.get("version", "")

        if not id_val:
            self._log_view.write("[校验失败] 信息 → id 不能为空")
            self._highlight_tab("信息")
            w = self._info_view._fields.get("id")
            if w:
                self._highlight_field(w)
            self._tab_view.set("信息")
            return False

        if not name_val:
            self._log_view.write("[校验失败] 信息 → name 不能为空")
            self._highlight_tab("信息")
            w = self._info_view._fields.get("name")
            if w:
                self._highlight_field(w)
            self._tab_view.set("信息")
            return False

        if not version_val:
            self._log_view.write("[校验失败] 信息 → version 不能为空")
            self._highlight_tab("信息")
            w = self._info_view._fields.get("version")
            if w:
                self._highlight_field(w)
            self._tab_view.set("信息")
            return False

        return True

    def _validate_dep_tab(self) -> bool:
        """Validate 依赖 tab. Returns True if valid."""
        # At least dghub-sdk is always included
        return True

    def _validate_dist_tab(self) -> bool:
        """Validate 发布 tab. Returns True if valid."""
        entry = self._dist_view.get_entry()
        if not entry:
            self._log_view.write("[校验失败] 发布 → 入口文件不能为空")
            self._highlight_tab("发布")
            self._highlight_field(self._dist_view._entry_entry)
            self._tab_view.set("发布")
            return False
        src_dir = self._source_dir or self._plugin_dir
        if src_dir and not (Path(src_dir) / entry).is_file():
            self._log_view.write(f"[校验失败] 发布 → 入口文件不存在: {entry}")
            self._highlight_tab("发布")
            self._highlight_field(self._dist_view._entry_entry)
            self._tab_view.set("发布")
            return False
        if not self._output_dir:
            self._log_view.write("[校验失败] 输出目录未选择")
            self._out_path_frame.configure(border_width=2, border_color="red")
            self._out_label.configure(text_color="red")
            return False
        return True

    # ------------------------------------------------------------------
    # build pipeline
    # ------------------------------------------------------------------

    def _start_build(self) -> None:
        if self._running:
            return
        if not self._plugin_dir:
            self._build_status.configure(text="请先选择插件目录", text_color="red")
            self._log_view.write("[错误] 请先选择插件目录")
            self._dir_path_frame.configure(border_width=2, border_color="red")
            self._dir_label.configure(text="请选择插件目录", text_color="red")
            return

        self._clear_error_styles()
        self._log_view.clear()
        self._build_success = False
        self._build_status.configure(text="构建中...", text_color=("gray40", "gray60"))
        self._running = True
        self._build_btn.configure(text="构建中...", state="disabled")

        # Run build in background
        threading.Thread(target=self._run_build, daemon=True).start()

    def _run_build(self) -> None:
        """Validate and execute the build pipeline."""
        try:
            # Step 1: validate
            self._log_view.write("=== 开始校验 ===")
            if not self._validate_info_tab():
                return
            if not self._validate_dep_tab():
                return
            if not self._validate_dist_tab():
                return
            self._log_view.write("校验通过 ✓")
            self._build_success = True

            # Step 2: save settings
            self._dist_view.save_settings()
            self._log_view.write("配置已保存")

            # Step 3: prepare paths
            plugin_dir = Path(self._plugin_dir)
            source_dir = Path(self._source_dir or self._plugin_dir)
            output_dir = Path(self._output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            plugin_name = plugin_dir.name
            build_exe = self._dist_view.get_build_exe()
            target = self._dist_view.get_target()

            # Step 4: pack vendor dependencies
            pkgs = self._dep_view.get_packages()
            if pkgs:
                # Filter out base deps and stdlib for the log
                valid_pkgs = [p for p in pkgs
                              if not is_dghub_base_dep(p) and not _is_stdlib(p)]
                if valid_pkgs:
                    self._log_view.write(f"打包 {len(valid_pkgs)} 个依赖...")
                    # Pack to a temp vendor dir in output
                    vendor_dir = output_dir / "vendor"
                    results = pack_dependencies(
                        valid_pkgs, vendor_dir,
                        method="auto",
                        progress_callback=self._log_view.write,
                    )
                    success = sum(1 for v in results.values() if v)
                    total = len(results)
                    self._log_view.write(f"依赖打包: {success}/{total} 成功")

            # Step 5: build exe if requested
            if build_exe:
                self._log_view.write("构建 exe...")
                include_sdk = self._dist_view.get_include_sdk()
                ok = build_plugin_exe(
                    plugin_dir=str(plugin_dir),
                    source_dir=str(source_dir),
                    include_dghub_sdk=include_sdk,
                    log_callback=self._log_view.write,
                    output_dir=str(output_dir),
                )
                if not ok:
                    self._log_view.write("[错误] exe 构建失败")
                    return
                # Cleanup PyInstaller artifacts from plugin dir
                for leftover in plugin_dir.glob("*.spec"):
                    leftover.unlink()
                build_dir = plugin_dir / "build"
                if build_dir.is_dir():
                    import shutil
                    shutil.rmtree(build_dir)
                self._log_view.write("exe 构建完成")

            # Step 6: generate manifest for output
            manifest_data = self._info_view._build_manifest()
            entry = self._dist_view.get_entry()
            if build_exe:
                entry = f"{plugin_name}.exe"
            manifest_data["entry"] = entry
            manifest_data.pop("homepage", None)

            # Step 7: create output
            if target == "zip":
                zip_path = output_dir / f"{plugin_name}.zip"
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    # Write manifest
                    zf.writestr("manifest.json",
                                json.dumps(manifest_data, ensure_ascii=False,
                                           indent=2))
                    # Write entry source (non-exe mode only)
                    if not build_exe:
                        entry_src = source_dir / entry
                        if entry_src.is_file():
                            zf.write(entry_src, entry_src.name)
                    # Write exe (exe mode)
                    if build_exe:
                        exe_path = output_dir / f"{plugin_name}.exe"
                        if exe_path.is_file():
                            zf.write(exe_path, exe_path.name)
                    # Write vendor/ (non-exe mode only)
                    vendor_src = output_dir / "vendor"
                    if vendor_src.is_dir():
                        for f in vendor_src.rglob("*"):
                            if f.is_file():
                                arc = f.relative_to(output_dir).as_posix()
                                zf.write(f, arc)
                    self._log_view.write(f"打包 zip: {zip_path}")
                size_kb = zip_path.stat().st_size / 1024
                self._log_view.write(f"[完成] {zip_path} ({size_kb:.1f} KB)")

            elif target == "folder":
                folder_dir = output_dir / plugin_name
                folder_dir.mkdir(parents=True, exist_ok=True)
                # Write manifest
                (folder_dir / "manifest.json").write_text(
                    json.dumps(manifest_data, ensure_ascii=False, indent=2),
                    encoding="utf-8")
                # Write entry/exe (same logic as zip)
                if not build_exe:
                    entry_src = source_dir / entry
                    if entry_src.is_file():
                        try:
                            (folder_dir / entry_src.name).write_bytes(
                                entry_src.read_bytes())
                        except Exception as exc:
                            self._log_view.write(
                                f"[警告] 复制入口文件失败: {exc}")
                    # Write vendor/
                    vendor_src = output_dir / "vendor"
                    if vendor_src.is_dir():
                        vendor_dst = folder_dir / "vendor"
                        import shutil
                        if vendor_dst.exists():
                            shutil.rmtree(vendor_dst)
                        vendor_src.rename(vendor_dst)
                if build_exe:
                    exe_path = output_dir / f"{plugin_name}.exe"
                    if exe_path.is_file():
                        try:
                            import shutil
                            shutil.copy2(exe_path, folder_dir / exe_path.name)
                        except Exception as exc:
                            self._log_view.write(f"[警告] 复制 exe 失败: {exc}")
                self._log_view.write(f"[完成] 文件夹已发布: {folder_dir}")

            # Cleanup temp vendor, cache, and exe (intermediate artifact)
            import shutil
            temp_vendor = output_dir / "vendor"
            if temp_vendor.is_dir():
                shutil.rmtree(temp_vendor)
            cache_dir = output_dir / "cache"
            if cache_dir.is_dir():
                shutil.rmtree(cache_dir)
            exe_file = output_dir / f"{plugin_name}.exe"
            if exe_file.is_file():
                exe_file.unlink()

        except Exception as exc:
            self._log_view.write(f"[错误] 构建失败: {exc}")
        finally:
            self._running = False
            self._build_btn.configure(text="构建", state="normal")
            if self._build_success:
                self._build_status.configure(text="✅ 构建成功", text_color="green")
            else:
                self._build_status.configure(text="❌ 构建失败", text_color="red")

    def _save_last_plugin_dir(self, d: str) -> None:
        try:
            _STATE_FILE.write_text(
                json.dumps({"last_plugin_dir": d}), encoding="utf-8")
        except Exception:
            pass

    def _auto_open_last_plugin_dir(self) -> None:
        try:
            if _STATE_FILE.is_file():
                data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
                last = data.get("last_plugin_dir", "")
                if last and Path(last).is_dir():
                    self._select_shared_dir(last)
        except Exception:
            pass

    def _select_shared_dir(self, d: str = "") -> None:
        if not d:
            d = filedialog.askdirectory(title="选择插件根目录")
            if not d:
                return
        self._plugin_dir = d
        self._dir_label.configure(text=_norm(d), text_color=("gray10", "gray90"))
        self._dir_path_frame.configure(border_width=0)

        # Initialize project manager
        self._pm = ProjectManager(d)

        # Push to all tabs
        self._info_view.set_plugin_dir(d, self._pm)
        self._dep_view.set_plugin_dir(d, self._pm)
        self._dist_view.set_plugin_dir(d, self._pm)

        # Restore saved settings, or use auto defaults
        project = self._pm.read_project()

        # Source dir
        saved_src = project.get("source_dir", "")
        if saved_src:
            self._source_dir = saved_src
            self._source_auto = False
            self._src_label.configure(text=_norm(saved_src), text_color=("gray10", "gray90"))
        else:
            self._source_dir = d
            self._source_auto = True
            self._src_label.configure(text=_norm(d), text_color=("gray60", "gray60"))
        self._src_path_frame.configure(border_width=0)

        # Enable source and output dir rows
        for b in self._src_btns + self._out_btns:
            b.configure(state="normal")

        # Output dir
        saved_out = project.get("output_dir", "")
        if saved_out:
            self._output_dir = saved_out
            self._out_label.configure(text=_norm(saved_out), text_color=("gray10", "gray90"))
            self._output_auto = False
        else:
            default_out = _norm(Path(d) / "output")
            self._out_label.configure(text=default_out, text_color=("gray60", "gray60"))
            self._output_dir = default_out
            self._output_auto = True
        self._dist_view.refresh_preview(self._output_dir)

        self._log_view.write(f"已加载项目: {d}")
        self._save_last_plugin_dir(d)

    def _save_source_dir(self, src_dir: str) -> None:
        """Persist source dir setting to project config."""
        if self._pm:
            project = self._pm.read_project()
            project["source_dir"] = src_dir
            self._pm.write_project(project)
