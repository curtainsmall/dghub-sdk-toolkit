"""Main application window — cross-tab layout with top/bottom bars."""

import datetime
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Optional


def _norm(p: str) -> str:
    """Normalize path separators to forward slashes."""
    return Path(p).as_posix()

import customtkinter as ctk

from gui.distribute_tab import DistributeTab
from backend.build_systems import (BUILD_SYSTEMS, BuildContext, BuildError,
                                   read_tool_dghub_entry)
from backend.build_runner import run_build
from backend.packaging import cleanup_intermediates
from gui.log_tab import LogTab
from backend.logbus import Logger
from backend.build_control import Canceller
from gui.manifest_tab import ManifestTab
from backend.project_manager import (ProjectManager, project_exists,
                                     UnsupportedFormatError)
from gui.settings_tab import SettingsTab
from gui.widgets import ToolTip
from backend import settings_store

# 构建系统下拉项 ↔ 存储值（由构建系统注册表生成）
_TYPE_LABELS = {bs_id: bs.label for bs_id, bs in BUILD_SYSTEMS.items()}
_TYPE_VALUES = {v: k for k, v in _TYPE_LABELS.items()}


class App(ctk.CTk):
    """DGHub SDK Packer main window."""

    TITLE = "DGHub SDK Packer"
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
        self._canceller: Optional[Canceller] = None  # 当前构建的取消令牌
        # 错误高亮登记表：tab 名 → 当前高亮的控件集合（用于级联清除）
        self._error_fields: dict[str, set] = {"信息": set(), "构建": set()}

        # -- top bar (cross-tab) --
        self._build_top_bar()

        # -- tab view --
        self._tab_view = ctk.CTkTabview(self, anchor="nw")
        self._tab_view.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)

        # -- tabs --
        self._info_tab = self._tab_view.add("信息")
        self._dist_tab = self._tab_view.add("构建")
        self._settings_tab = self._tab_view.add("设置")
        self._log_tab = self._tab_view.add("日志")

        # -- populate tabs --
        self._info_view = ManifestTab(
            self._info_tab, on_field_edit=self._on_info_field_edit)
        self._info_view.pack(fill="both", expand=True)

        self._dist_view = DistributeTab(
            self._dist_tab,
            on_select_source=self._select_source_dir,
            on_reset_source=self._reset_source_dir,
            on_entry_edit=self._on_dist_entry_edit)
        self._dist_view.pack(fill="both", expand=True)

        self._settings_view = SettingsTab(
            self._settings_tab,
            on_pypi_index_changed=lambda url: self._save_state_key(
                "pypi_index", url))
        self._settings_view.pack(fill="both", expand=True)

        self._log_view = LogTab(self._log_tab)
        self._log_view.pack(fill="both", expand=True)
        self._logger = Logger(self._log_view.emit)

        # -- bottom bar (cross-tab) --
        self._build_bottom_bar()

        # -- restore global settings --
        self._settings_view.set_pypi_index(
            self._read_state().get("pypi_index", ""))

        # -- auto-load last plugin dir --
        self._auto_open_last_plugin_dir()

        # 退出时终止正在运行的构建（避免残留子进程）
        self.protocol("WM_DELETE_WINDOW", self._on_close)

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
                ToolTip(reset_btn, "恢复默认")
                btns.append(reset_btn)
            return frame, lbl, btns
        
        # Row 0: 插件目录（始终可用）
        self._dir_path_frame, self._dir_label, self._dir_btns = _make_dir_row(
            bar, 0, "插件目录:", "未选择", self._select_shared_dir)
        
        # Row 1: 输出目录（初始禁用；源码/收集目录已移入构建 tab 各系统视图）
        self._out_path_frame, self._out_label, self._out_btns = _make_dir_row(
            bar, 1, "输出目录:", "", self._select_output_dir,
            reset_cmd=self._reset_output_dir)
        self._out_reset_btn = self._out_btns[1]
        
        # Row 2: 构建系统（跨 tab 全局选择器，初始禁用；右侧为系统说明文案）
        ctk.CTkLabel(bar, text="构建系统:",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=2, column=0, padx=(0, 5), pady=4, sticky="w")
        self._build_system = "uv"
        type_frame = ctk.CTkFrame(bar, fg_color="transparent")
        type_frame.grid(row=2, column=1, sticky="ew", padx=5, pady=4)
        self._type_menu = ctk.CTkOptionMenu(
            type_frame, width=200, values=list(_TYPE_LABELS.values()),
            command=self._on_build_system_changed)
        self._type_menu.set(_TYPE_LABELS["uv"])
        self._type_menu.pack(side="left")
        self._type_menu.configure(state="disabled")
        # width=1：固定请求宽度，长文案不撑宽顶部栏
        self._type_hint = ctk.CTkLabel(
            type_frame, text="", font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"), anchor="w", width=1)
        self._type_hint.pack(side="left", fill="x", expand=True, padx=(10, 0))
        
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

    def _update_type_hint(self) -> None:
        """刷新选择器右侧的构建系统说明文案（空描述则不显示）。"""
        bs = BUILD_SYSTEMS.get(self._build_system)
        self._type_hint.configure(text=bs.description if bs else "")

    def _on_build_system_changed(self, label: str) -> None:
        """构建系统切换：持久化、加载新系统目录状态并切换视图。"""
        self._build_system = _TYPE_VALUES.get(label, "uv")
        self._update_type_hint()
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
            bar, text="开始构建", command=self._start_build,
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
        """构建 tab 视图内锚点行的选择回调（按当前系统持久化）。

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
            bs = BUILD_SYSTEMS[self._build_system]
            patterns = bs.manifest_patterns or ("*.*",)
            f = filedialog.askopenfilename(
                title=f"选择依赖清单 ({bs.dep_manifest_hint})",
                initialdir=self._plugin_dir,
                filetypes=[("依赖清单", patterns), ("所有文件", "*.*")])
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
                self._logger.info(
                    f"已从 [tool.dghub] 自动填充入口: {auto_entry}")
        self._dist_view.set_source_dir(self._source_dir)
        self._push_source_display()
        self._dist_view.clear_entry_error()
        self._clear_field_error("构建", self._dist_view._entry_entry)
        self._clear_field_error("构建", self._dist_view._entry_generic_entry)

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
        self._clear_field_error("构建", self._dist_view._entry_entry)
        self._clear_field_error("构建", self._dist_view._entry_generic_entry)

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
        self._clear_field_error("构建", self._out_path_frame)

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
            self._clear_field_error("构建", self._out_path_frame)

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
        # 输出目录：自动默认时保持灰字，手动设置时用正常深色
        self._out_label.configure(
            text_color=("gray60", "gray60") if self._output_auto
            else ("gray10", "gray90"))
        # 视图内目录行/entry 红框复位
        self._dist_view.clear_entry_error()
        self._push_source_display()
        # 信息页必填字段红框复位（恢复默认灰边）
        self._info_view.reset_field_borders()
        # Reset tab colors
        self._tab_view._segmented_button._buttons_dict["信息"].configure(
            text_color=("gray10", "gray90"))
        self._tab_view._segmented_button._buttons_dict["构建"].configure(
            text_color=("gray10", "gray90"))
        # 清空错误登记表
        self._error_fields = {"信息": set(), "构建": set()}

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

    def _highlight_field(self, widget: Any, tab: str) -> None:
        """Apply red border to a CTkEntry and register it under its tab."""
        try:
            widget.configure(border_width=2, border_color="#FF4444")
        except Exception:
            pass
        self._error_fields.setdefault(tab, set()).add(widget)

    def _clear_field_error(self, tab: str, widget: Any = None) -> None:
        """字段修正后的级联清除：移出登记表 → tab 无错则清标题 → 复位状态。

        控件自身的红框由各来源（信息页 keyrelease / 构建页 entry / 输出目录
        选择）就地清除，此处只负责跨控件的 tab 标题高亮与「构建失败」标签。
        """
        fields = self._error_fields.get(tab)
        if fields is not None and widget is not None:
            fields.discard(widget)
        if not self._error_fields.get(tab):
            self._clear_tab_highlight(tab)
        self._reset_build_status_if_failed()

    def _reset_build_status_if_failed(self) -> None:
        """用户开始修正错误时，移除过时的「构建失败/成功」状态标签。"""
        if self._running:
            return
        self._build_status.configure(text="", text_color=("gray10", "gray90"))

    def _on_info_field_edit(self, key: str) -> None:
        """信息页字段被编辑（来自 ManifestTab 回调）→ 级联清除高亮。"""
        self._clear_field_error("信息", self._info_view._fields.get(key))

    def _on_dist_entry_edit(self) -> None:
        """构建页入口被编辑（来自 DistributeTab 回调）→ 级联清除高亮。"""
        widget = (self._dist_view._entry_generic_entry
                  if self._build_system == "generic"
                  else self._dist_view._entry_entry)
        self._clear_field_error("构建", widget)

    def _validate_info_tab(self) -> bool:
        """Validate 信息 tab fields，一次性检测所有必填项。Returns True if valid."""
        manifest = self._info_view._build_manifest()
        ok = True
        for key, label in (("id", "id"), ("name", "name"),
                           ("version", "version")):
            if not manifest.get(key, ""):
                self._logger.error(f"信息 → {label} 不能为空")
                self._highlight_tab("信息")
                w = self._info_view._fields.get(key)
                if w:
                    self._highlight_field(w, "信息")
                ok = False
        return ok

    def _validate_dist_tab(self) -> bool:
        """Validate 构建 tab，一次性检测入口与输出目录。Returns True if valid."""
        bs = BUILD_SYSTEMS[self._build_system]
        ctx = self._make_build_context()
        ok = True
        errors = bs.validate(ctx)
        if errors:
            for msg in errors:
                self._logger.error(f"构建 → {msg}")
            self._highlight_tab("构建")
            # 入口类错误同时红框对应 entry 控件
            if any("入口" in msg for msg in errors):
                entry_widget = (self._dist_view._entry_generic_entry
                                if self._build_system == "generic"
                                else self._dist_view._entry_entry)
                self._highlight_field(entry_widget, "构建")
            ok = False
        if not self._output_dir:
            self._logger.error("输出目录未选择")
            self._out_path_frame.configure(border_width=2, border_color="red")
            self._out_label.configure(text_color="red")
            self._highlight_tab("构建")
            self._error_fields["构建"].add(self._out_path_frame)
            ok = False
        return ok

    def _make_build_context(self) -> BuildContext:
        """组装校验/构建共用的上下文。"""
        plugin_dir = Path(self._plugin_dir or ".")
        return BuildContext(
            plugin_dir=plugin_dir,
            source_dir=Path(self._source_dir or self._plugin_dir or "."),
            output_dir=Path(self._output_dir) if self._output_dir else plugin_dir / "output",
            plugin_name=plugin_dir.name,
            dist_view=self._dist_view,
            log=self._logger,
            pypi_index=self._settings_view.get_pypi_index(),
            canceller=self._canceller,
        )

    # ------------------------------------------------------------------
    # build pipeline
    # ------------------------------------------------------------------

    def _lock_controls(self, locked: bool) -> None:
        """构建期间锁定构建系统选择、目录按钮与两个编辑 tab；结束后恢复。"""
        state = "disabled" if locked else "normal"
        try:
            self._type_menu.configure(state=state)
        except Exception:
            pass
        for b in getattr(self, "_dir_btns", []) + self._out_btns:
            try:
                b.configure(state=state)
            except Exception:
                pass
        self._info_view._set_enabled(not locked)
        self._dist_view._set_enabled(not locked)

    def _start_build(self) -> None:
        if self._running:
            return
        if not self._plugin_dir:
            self._build_status.configure(text="请先选择插件目录", text_color="red")
            self._logger.error("请先选择插件目录")
            self._dir_path_frame.configure(border_width=2, border_color="red")
            self._dir_label.configure(text="请选择插件目录", text_color="red")
            return

        self._clear_error_styles()
        self._logger.separator(
            f"构建 {datetime.datetime.now().strftime('%H:%M:%S')}")
        self._build_success = False
        self._build_status.configure(text="构建中...", text_color=("gray40", "gray60"))
        self._running = True
        self._canceller = Canceller()
        # 按钮转为「取消构建」（构建中其它控件锁定，唯此键可点）
        self._build_btn.configure(text="取消构建", command=self._cancel_build)
        # 锁定构建系统选择与所有编辑控件，避免构建期间状态被改动
        self._lock_controls(True)

        # Run build in background
        threading.Thread(target=self._run_build, daemon=True).start()

    def _cancel_build(self) -> None:
        """取消构建：对话框二次确认后硬终止子进程树。"""
        if not self._running:
            return
        if not messagebox.askyesno(
                "取消构建",
                "确定取消当前构建？\n正在运行的命令（pre-build / 依赖安装 / "
                "打包）将被立即终止。"):
            return
        if not self._running or self._canceller is None:
            return  # 对话框期间构建可能已结束
        self._canceller.cancel()
        self._logger.warning("正在取消构建...")
        self._build_status.configure(text="正在取消...",
                                     text_color=("gray50", "gray60"))

    def _on_close(self) -> None:
        """窗口关闭：若构建进行中，先终止子进程再退出（不弹框）。"""
        if self._running and self._canceller is not None:
            self._canceller.cancel()
        self.destroy()

    def _run_build(self) -> None:
        """Validate and execute the build pipeline."""
        ctx = None
        try:
            # Step 1: validate（一次性检测两个 tab 的所有字段）
            self._logger.info("开始校验")
            info_ok = self._validate_info_tab()
            dist_ok = self._validate_dist_tab()
            if not (info_ok and dist_ok):
                self._tab_view.set("信息" if not info_ok else "构建")
                return
            self._logger.info("校验通过")
            self._build_success = True

            # Step 2: save settings
            self._dist_view.save_settings()
            self._logger.detail("配置已保存")

            # Step 3: prepare context
            bs = BUILD_SYSTEMS[self._build_system]
            ctx = self._make_build_context()
            ctx.output_dir.mkdir(parents=True, exist_ok=True)
            target = self._dist_view.get_target()
            manifest_data = self._info_view._build_manifest()

            # Step 4: 构建 + 打包（GUI/CLI 共用的后端编排）
            try:
                artifact = run_build(ctx, bs, manifest_data, target)
            except BuildError as be:
                for msg in be.errors:
                    self._logger.error(msg)
                self._highlight_tab("构建")
                self._build_success = False
                return
            if artifact is None:
                self._build_success = False
                return

        except Exception as exc:
            self._logger.error(f"构建失败: {exc}")
        finally:
            self._running = False
            # 按钮恢复为「开始构建」
            self._build_btn.configure(text="开始构建", state="normal",
                                      command=self._start_build)
            # 解锁构建系统选择与编辑控件
            self._lock_controls(False)
            cancelled = (self._canceller is not None
                         and self._canceller.cancelled)
            if cancelled:
                # 取消后清理已产生的中间产物（仅 output_dir，不动用户源目录）
                if ctx is not None:
                    cleanup_intermediates(ctx.output_dir, ctx.plugin_name)
                self._logger.warning("构建已取消")
                self._build_status.configure(text="⏹ 已取消",
                                             text_color=("gray50", "gray60"))
            elif self._build_success:
                self._build_status.configure(text="✅ 构建成功", text_color="green")
            else:
                self._build_status.configure(text="❌ 构建失败", text_color="red")
            self._canceller = None

    def _read_state(self) -> dict:
        """读取全局状态（委托 backend.settings_store）。"""
        return settings_store.read_state()

    def _save_state_key(self, key: str, value: Any) -> None:
        """更新全局状态的单个键（委托 backend.settings_store）。"""
        settings_store.save_state_key(key, value)

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
        self._pm = ProjectManager(d, log=self._logger)
        try:
            project = self._pm.read_project()
        except UnsupportedFormatError as exc:
            self._logger.error(str(exc))
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
        self._update_type_hint()
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

        self._logger.info(f"已加载项目: {d}")
        self._save_last_plugin_dir(d)
