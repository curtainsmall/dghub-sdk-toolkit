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

from distribute_tab import DistributeTab
from build_systems import (BUILD_SYSTEMS, BuildContext, BuildError,
                           read_tool_dghub_entry)
from log_tab import LogTab
from manifest_tab import ManifestTab
from project_manager import (ProjectManager, project_exists,
                             UnsupportedFormatError)
from settings_tab import SettingsTab

_STATE_DIR = Path.home() / ".dghub-sdk-packer"
_STATE_DIR.mkdir(parents=True, exist_ok=True)
_STATE_FILE = _STATE_DIR / "state.json"

# 构建系统下拉项 ↔ 存储值（由构建系统注册表生成）
_TYPE_LABELS = {bs_id: bs.label for bs_id, bs in BUILD_SYSTEMS.items()}
_TYPE_VALUES = {v: k for k, v in _TYPE_LABELS.items()}


class _ToolTip:
    """Lightweight hover tooltip for a widget."""

    def __init__(self, widget: Any, text: str) -> None:
        self._widget = widget
        self._text = text
        self._tip: Optional[Any] = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event: Any = None) -> None:
        if self._tip is not None:
            return
        import tkinter as tk
        x = self._widget.winfo_rootx()
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tip = tk.Toplevel(self._widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self._tip, text=self._text, background="#333333",
                 foreground="white", padx=6, pady=2).pack()

    def _hide(self, _event: Any = None) -> None:
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


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
        self._build_system = "uv"

        # -- top bar (cross-tab) --
        self._build_top_bar()

        # -- tab view --
        self._tab_view = ctk.CTkTabview(self, anchor="nw")
        self._tab_view.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)

        # -- tabs --
        self._info_tab = self._tab_view.add("信息")
        self._dist_tab = self._tab_view.add("发布")
        self._settings_tab = self._tab_view.add("设置")
        self._log_tab = self._tab_view.add("日志")

        # -- populate tabs --
        self._info_view = ManifestTab(self._info_tab)
        self._info_view.pack(fill="both", expand=True)

        self._dist_view = DistributeTab(
            self._dist_tab,
            on_select_source=self._select_source_dir,
            on_reset_source=self._reset_source_dir)
        self._dist_view.pack(fill="both", expand=True)

        self._settings_view = SettingsTab(
            self._settings_tab,
            on_pypi_index_changed=lambda url: self._save_state_key(
                "pypi_index", url))
        self._settings_view.pack(fill="both", expand=True)

        self._log_view = LogTab(self._log_tab)
        self._log_view.pack(fill="both", expand=True)

        # -- bottom bar (cross-tab) --
        self._build_bottom_bar()

        # -- restore global settings --
        self._settings_view.set_pypi_index(
            self._read_state().get("pypi_index", ""))

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
            # Fixed-width slot reserves reset button space so the
            # select button column never shifts when reset toggles
            slot = ctk.CTkFrame(btn_frame, fg_color="transparent",
                                width=33, height=28)
            slot.pack(side="left")
            slot.pack_propagate(False)
            if reset_cmd:
                reset_btn = ctk.CTkButton(slot, text="↺", width=28,
                        command=reset_cmd, fg_color="transparent",
                        hover_color=("gray70", "gray40"),
                        font=ctk.CTkFont(size=16))
                # Hidden by default; shown only when dir is manually set
                _ToolTip(reset_btn, "恢复默认")
                btns.append(reset_btn)
            return frame, lbl, btns
        
        # Row 0: 插件目录（始终可用）
        self._dir_path_frame, self._dir_label, _ = _make_dir_row(
            bar, 0, "插件目录:", "未选择", self._select_shared_dir)
        
        # Row 1: 输出目录（初始禁用；源码/收集目录已移入发布 tab 各系统视图）
        self._out_path_frame, self._out_label, self._out_btns = _make_dir_row(
            bar, 1, "输出目录:", "", self._select_output_dir,
            reset_cmd=self._reset_output_dir)
        self._out_reset_btn = self._out_btns[1]
        
        # Row 2: 构建系统（跨 tab 全局选择器，初始禁用）
        ctk.CTkLabel(bar, text="构建系统:",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=2, column=0, padx=(0, 5), pady=4, sticky="w")
        self._build_system = "uv"
        self._type_menu = ctk.CTkOptionMenu(
            bar, width=200, values=list(_TYPE_LABELS.values()),
            command=self._on_build_system_changed)
        self._type_menu.set(_TYPE_LABELS["uv"])
        self._type_menu.grid(row=2, column=1, padx=5, pady=4, sticky="w")
        self._type_menu.configure(state="disabled")
        
        # Initially disable output row
        for b in self._out_btns:
            b.configure(state="disabled")

    @staticmethod
    def _set_reset_visible(btn: Any, visible: bool) -> None:
        """Show/hide a reset button (visible only when dir is manually set)."""
        if visible:
            btn.pack(side="left", padx=(5, 0))
        else:
            btn.pack_forget()

    def _on_build_system_changed(self, label: str) -> None:
        """构建系统切换：持久化、加载新系统目录状态并切换视图。"""
        self._build_system = _TYPE_VALUES.get(label, "uv")
        if self._pm:
            project = self._pm.read_project()
            project["build_system"] = self._build_system
            self._pm.write_project(project)
            # source_dir 按系统独立，切换后从新系统的命名空间重新加载
            self._load_source_dir_state()
        self._dist_view.set_build_system(self._build_system)
        if self._output_dir:
            self._dist_view.refresh_preview(self._output_dir)

    def _view_key(self) -> str:
        """当前系统对应的视图/目录行 key（uv/pip 共用 python 行）。"""
        return "generic" if self._build_system == "generic" else "python"

    def _load_source_dir_state(self) -> None:
        """从当前系统命名空间加载项目根锚点并刷新视图显示。

        uv/pip：锚点 = 选定的依赖清单，项目根 = 清单所在目录；
        generic：锚点 = 收集目录。未设置时均回退插件目录。
        """
        if not self._pm or not self._plugin_dir:
            return
        cfg = self._pm.get_bs_config(self._build_system)
        if self._build_system == "generic":
            stored = cfg.get("source_dir", "")
            self._source_dir = (self._pm.to_absolute(stored) if stored
                                else self._plugin_dir)
            self._source_auto = not stored
            self._dist_view.set_manifest("")
        else:
            stored = cfg.get("manifest", "")
            if stored:
                manifest_abs = self._pm.to_absolute(stored)
                self._source_dir = str(Path(manifest_abs).parent)
                self._source_auto = False
                self._dist_view.set_manifest(manifest_abs)
            else:
                self._source_dir = self._plugin_dir
                self._source_auto = True
                self._dist_view.set_manifest("")
        self._dist_view.set_source_dir(self._source_dir)
        self._push_source_display()

    def _push_source_display(self) -> None:
        """向两个视图推送各自的锚点显示（按系统独立取值）。"""
        if not self._pm or not self._plugin_dir:
            return
        # python 行显示 Python 系构建系统（uv）选定的清单文件
        stored = self._pm.get_bs_config("uv").get("manifest", "")
        if stored:
            self._dist_view.set_source_display(
                "python", _norm(self._pm.to_absolute(stored)), False)
        else:
            self._dist_view.set_source_display(
                "python", "未选择（项目根 = 插件目录）", True)
        # generic 行显示收集目录
        stored = self._pm.get_bs_config("generic").get("source_dir", "")
        path = self._pm.to_absolute(stored) if stored else self._plugin_dir
        self._dist_view.set_source_display("generic", _norm(path), not stored)

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
        """发布 tab 视图内锚点行的选择回调（按当前系统持久化）。

        generic 选收集目录；uv/pip 选依赖清单文件（项目根 = 其所在目录）。
        """
        if self._build_system == "generic":
            d = filedialog.askdirectory(title="选择收集目录")
            if not d:
                return
            self._source_dir = d
            self._source_auto = False
            if self._pm:
                self._pm.set_bs_config("generic", "source_dir",
                                       self._pm.to_relative(d))
        else:
            hint = BUILD_SYSTEMS[self._build_system].dep_manifest_hint
            f = filedialog.askopenfilename(
                title=f"选择依赖清单 ({hint})",
                initialdir=self._plugin_dir,
                filetypes=[(hint, hint), ("所有文件", "*.*")])
            if not f:
                return
            self._source_dir = str(Path(f).parent)
            self._source_auto = False
            if self._pm:
                self._pm.set_bs_config(self._build_system, "manifest",
                                       self._pm.to_relative(f))
            self._dist_view.set_manifest(_norm(f))
            # 可选约定：pyproject.toml 的 [tool.dghub].entry 自动填充入口
            auto_entry = read_tool_dghub_entry(Path(f))
            if auto_entry:
                self._dist_view.set_entry(auto_entry)
                self._log_view.write(
                    f"已从 [tool.dghub] 自动填充入口: {auto_entry}")
        self._dist_view.set_source_dir(self._source_dir)
        self._push_source_display()
        self._dist_view.clear_entry_error()
        self._clear_tab_highlight("发布")

    def _reset_source_dir(self) -> None:
        """重置当前系统的锚点（generic 回插件目录；uv/pip 清除清单）。"""
        if not self._plugin_dir:
            return
        self._source_dir = self._plugin_dir
        self._source_auto = True
        if self._pm:
            if self._build_system == "generic":
                self._pm.set_bs_config("generic", "source_dir", "")
            else:
                self._pm.set_bs_config(self._build_system, "manifest", "")
                self._dist_view.set_manifest("")
        self._dist_view.set_source_dir(self._plugin_dir)
        self._push_source_display()
        self._dist_view.clear_entry_error()
        self._clear_tab_highlight("发布")

    def _select_output_dir(self) -> None:
        d = filedialog.askdirectory(title="选择输出目录")
        if not d:
            return
        self._output_dir = d
        self._out_label.configure(text=_norm(d), text_color=("gray10", "gray90"))
        self._output_auto = False
        self._out_path_frame.configure(border_width=0)
        self._set_reset_visible(self._out_reset_btn, True)
        self._dist_view.refresh_preview(_norm(d))
        self._save_output_dir(_norm(d))

    def _reset_output_dir(self) -> None:
        """Reset output dir to default (plugin_dir/output)."""
        if self._plugin_dir:
            default_out = _norm(Path(self._plugin_dir) / "output")
            self._output_dir = default_out
            self._out_label.configure(text=default_out, text_color=("gray60", "gray60"))
            self._output_auto = True
            self._out_path_frame.configure(border_width=0)
            self._set_reset_visible(self._out_reset_btn, False)
            self._dist_view.refresh_preview(default_out)
            self._save_output_dir("")

    def _save_output_dir(self, out_dir: str) -> None:
        """Persist output dir setting to project config (存相对插件目录)。"""
        if self._pm:
            project = self._pm.read_project()
            project["output_dir"] = self._pm.to_relative(out_dir)
            self._pm.write_project(project)

    # ------------------------------------------------------------------
    # validation
    # ------------------------------------------------------------------

    def _clear_error_styles(self) -> None:
        """Reset all error states."""
        self._dir_path_frame.configure(border_width=0, border_color="")
        self._dir_label.configure(text_color=("gray10", "gray90"))
        self._out_path_frame.configure(border_width=0, border_color="")
        self._out_label.configure(text_color=("gray10", "gray90"))
        # 视图内目录行/entry 红框复位
        self._dist_view.clear_entry_error()
        self._push_source_display()
        # Reset tab colors
        self._tab_view._segmented_button._buttons_dict["信息"].configure(
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

    def _validate_dist_tab(self) -> bool:
        """Validate 发布 tab：系统相关静态校验委派给当前系统对象。"""
        bs = BUILD_SYSTEMS[self._build_system]
        ctx = self._make_build_context()
        errors = bs.validate(ctx)
        if errors:
            for msg in errors:
                self._log_view.write(f"[校验失败] 发布 → {msg}")
            self._highlight_tab("发布")
            # 入口类错误同时红框对应 entry 控件
            if any("入口" in msg for msg in errors):
                entry_widget = (self._dist_view._entry_generic_entry
                                if self._build_system == "generic"
                                else self._dist_view._entry_entry)
                self._highlight_field(entry_widget)
            self._tab_view.set("发布")
            return False
        if not self._output_dir:
            self._log_view.write("[校验失败] 输出目录未选择")
            self._out_path_frame.configure(border_width=2, border_color="red")
            self._out_label.configure(text_color="red")
            return False
        return True

    def _make_build_context(self) -> BuildContext:
        """组装校验/构建共用的上下文。"""
        plugin_dir = Path(self._plugin_dir or ".")
        return BuildContext(
            plugin_dir=plugin_dir,
            source_dir=Path(self._source_dir or self._plugin_dir or "."),
            output_dir=Path(self._output_dir) if self._output_dir else plugin_dir / "output",
            plugin_name=plugin_dir.name,
            dist_view=self._dist_view,
            log=self._log_view.write,
            pypi_index=self._settings_view.get_pypi_index(),
        )

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
            if not self._validate_dist_tab():
                return
            self._log_view.write("校验通过 ✓")
            self._build_success = True

            # Step 2: save settings
            self._dist_view.save_settings()
            self._log_view.write("配置已保存")

            # Step 3: prepare context
            bs = BUILD_SYSTEMS[self._build_system]
            ctx = self._make_build_context()
            ctx.output_dir.mkdir(parents=True, exist_ok=True)
            target = self._dist_view.get_target()

            # Step 4: 系统特有构建步骤（uv/pip: 依赖 vendor + 可选 exe；
            # generic: 可选 pre-build）
            if not bs.build_steps(ctx):
                self._build_success = False
                return

            # Step 5: generate manifest for output
            manifest_data = self._info_view._build_manifest()
            manifest_data["entry"] = bs.manifest_entry(ctx)
            manifest_data.pop("homepage", None)
            manifest_json = json.dumps(manifest_data, ensure_ascii=False,
                                       indent=2)

            # Step 6: 收集产物清单（含存在性校验与 glob 求值，在
            # pre-build 之后执行）并统一打包（zip 与 folder 结构一致）
            try:
                out_files = bs.collect_output(ctx)
            except BuildError as be:
                for msg in be.errors:
                    self._log_view.write(f"[构建失败] {msg}")
                self._highlight_tab("发布")
                self._build_success = False
                return
            if target == "zip":
                zip_path = ctx.output_dir / f"{ctx.plugin_name}.zip"
                with zipfile.ZipFile(zip_path, "w",
                                     zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr("manifest.json", manifest_json)
                    for src, arc in out_files:
                        zf.write(src, arc)
                    self._log_view.write(f"打包 zip: {zip_path}")
                size_kb = zip_path.stat().st_size / 1024
                self._log_view.write(f"[完成] {zip_path} ({size_kb:.1f} KB)")
            elif target == "folder":
                import shutil
                folder_dir = ctx.output_dir / ctx.plugin_name
                folder_dir.mkdir(parents=True, exist_ok=True)
                (folder_dir / "manifest.json").write_text(
                    manifest_json, encoding="utf-8")
                for src, arc in out_files:
                    dst = folder_dir / arc
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(src, dst)
                    except Exception as exc:
                        self._log_view.write(f"[警告] 复制文件失败: {exc}")
                self._log_view.write(f"[完成] 文件夹已发布: {folder_dir}")

            # Cleanup temp vendor, cache, and exe (intermediate artifact)
            import shutil
            temp_vendor = ctx.output_dir / "vendor"
            if temp_vendor.is_dir():
                shutil.rmtree(temp_vendor)
            cache_dir = ctx.output_dir / "cache"
            if cache_dir.is_dir():
                shutil.rmtree(cache_dir)
            exe_file = ctx.output_dir / f"{ctx.plugin_name}.exe"
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

    def _read_state(self) -> dict:
        """读取全局状态文件（不存在或损坏返回空 dict）。"""
        try:
            if _STATE_FILE.is_file():
                return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_state_key(self, key: str, value: Any) -> None:
        """读-改-写更新全局状态文件的单个键（不覆盖其他键）。"""
        try:
            state = self._read_state()
            state[key] = value
            _STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
        except Exception:
            pass

    def _save_last_plugin_dir(self, d: str) -> None:
        self._save_state_key("last_plugin_dir", d)

    def _auto_open_last_plugin_dir(self) -> None:
        try:
            last = self._read_state().get("last_plugin_dir", "")
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

        # Initialize project manager（旧格式破坏性升级：重置为默认值并日志提示）
        self._pm = ProjectManager(d, log=self._log_view.write)
        try:
            project = self._pm.read_project()
        except UnsupportedFormatError as exc:
            self._log_view.write(f"[错误] {exc}")
            self._pm = None
            return

        # Push to all tabs
        self._info_view.set_plugin_dir(d, self._pm)
        self._dist_view.set_plugin_dir(d, self._pm)

        # Build system
        self._build_system = project.get("build_system", "uv")
        if self._build_system not in BUILD_SYSTEMS:
            self._build_system = "uv"
        self._type_menu.configure(state="normal")
        self._type_menu.set(_TYPE_LABELS.get(self._build_system,
                                             _TYPE_LABELS["uv"]))
        self._dist_view.set_build_system(self._build_system)

        # Source dir（按系统独立：加载当前系统并刷新两个视图的显示）
        self._load_source_dir_state()

        # Enable output dir row
        for b in self._out_btns:
            b.configure(state="normal")

        # Output dir（存储为相对插件目录，解析为绝对后使用）
        saved_out = project.get("output_dir", "")
        if saved_out:
            self._output_dir = self._pm.to_absolute(saved_out)
            self._out_label.configure(text=_norm(self._output_dir),
                                      text_color=("gray10", "gray90"))
            self._output_auto = False
        else:
            default_out = _norm(Path(d) / "output")
            self._out_label.configure(text=default_out, text_color=("gray60", "gray60"))
            self._output_dir = default_out
            self._output_auto = True
        self._set_reset_visible(self._out_reset_btn, not self._output_auto)
        self._dist_view.refresh_preview(self._output_dir)

        self._log_view.write(f"已加载项目: {d}")
        self._save_last_plugin_dir(d)
