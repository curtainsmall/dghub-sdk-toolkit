"""Distribute tab — 打包内容、构建选项与发布目标（按构建系统双视图）。

Python 式视图（uv / pip 共用）：依赖来源面板 + 源码目录 + entry + 构建选项 + 发布目标。
(无构建系统) 视图：附加文件/规则清单 + 收集目录 + pre-build（含执行目录）+ entry + 发布目标。
两视图整帧切换，发布目标与预览共享状态；目录行各自绑定自己系统的 source_dir。
"""

import subprocess
import threading
from pathlib import Path
from tkinter import filedialog
from typing import Any, Callable, Optional

import customtkinter as ctk

from build_systems import BUILD_SYSTEMS, evaluate_pattern
from exe_builder import _NO_WINDOW, _get_python_exe
from project_manager import ProjectManager

# 目标位置显示名 ↔ 存储值
_DEST_LABELS = {"root": "根目录", "vendor": "vendor/"}
_DEST_VALUES = {v: k for k, v in _DEST_LABELS.items()}

# 右栏各行统一的前导标签宽度（像素）：保证输入框/目录显示区左对齐
_LABEL_W = 92
# 右栏各行尾部（选择按钮 + 重置槽位）总宽：无按钮的行用等宽占位，
# 使所有输入区右边界一致、选择按钮列对齐
_SELECT_BTN_W = 90
_RESET_SLOT_W = 33


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


class DistributeTab(ctk.CTkFrame):
    """构建 tab：双视图容器（python_view / generic_view）+ 共享预览。"""

    def __init__(self, master: Any,
                 on_select_source: Optional[Callable[[], None]] = None,
                 on_reset_source: Optional[Callable[[], None]] = None,
                 **kwargs: Any) -> None:
        super().__init__(master, **kwargs)
        self._pm: Optional[ProjectManager] = None
        self._plugin_dir: Optional[str] = None
        self._source_dir: Optional[str] = None
        self._manifest_path = ""
        self._bs = "uv"
        self._loading = False
        self._extra_files: list[dict[str, str]] = []
        self._exec_dir = ""  # pre-build 执行目录（绝对路径；空 = 插件目录）
        self._enabled = False
        # app.py 注入的目录选择/重置回调（目录状态由 App 统一管理）
        self._on_select_source = on_select_source
        self._on_reset_source = on_reset_source
        self._src_rows: dict[str, dict[str, Any]] = {}
        self._build_ui()
        self._set_enabled(False)

    def _set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self._enabled = enabled
        for w in self._controls:
            try:
                w.configure(state=state)
            except Exception:
                pass
        self._update_exec_state()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=3)
        self.grid_rowconfigure(1, weight=2)

        self._controls: list[ctk.CTkBaseClass] = []

        # 共享变量（python 式视图与 generic 视图各用各的 entry 变量）
        self._entry_var = ctk.StringVar(value="main.py")
        self._entry_generic_var = ctk.StringVar(value="")
        self._pre_build_var = ctk.StringVar(value="")
        self._build_exe_var = ctk.BooleanVar(value=True)
        self._include_sdk_var = ctk.BooleanVar(value=True)
        self._target_var = ctk.StringVar(value="zip")

        # 上区双视图（同一 grid 单元格，整帧切换）
        self._python_view = ctk.CTkFrame(self, fg_color="transparent")
        self._python_view.grid(row=0, column=0, sticky="nsew")
        self._build_python_view(self._python_view)

        self._generic_view = ctk.CTkFrame(self, fg_color="transparent")
        self._generic_view.grid(row=0, column=0, sticky="nsew")
        self._build_generic_view(self._generic_view)
        self._generic_view.grid_remove()

        # 下区预览（横向撑满，两视图共享）
        self._build_preview(self)

        # 变更即保存
        self._entry_var.trace_add("write", self._on_setting_changed)
        self._entry_generic_var.trace_add("write", self._on_setting_changed)
        self._pre_build_var.trace_add("write", self._on_setting_changed)
        # pre-build 有无决定执行目录行的可用性
        self._pre_build_var.trace_add(
            "write", lambda *a: self._update_exec_state())
        self._build_exe_var.trace_add("write", self._on_setting_changed)
        self._include_sdk_var.trace_add("write", self._on_setting_changed)
        self._target_var.trace_add("write", self._on_setting_changed)

    # -- 目录行（两视图各一行，绑定各自系统的 source_dir） --------------

    def _build_source_row(self, parent: ctk.CTkFrame, row: int,
                          key: str, label: str,
                          btn_text: str = "选择目录") -> None:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=10, pady=(10, 0))
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text=label, width=_LABEL_W, anchor="w",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=(0, 5), sticky="w")

        path_frame = ctk.CTkFrame(frame, fg_color=("gray85", "gray25"),
                                  border_width=0, corner_radius=6)
        path_frame.grid(row=0, column=1, sticky="ew", padx=5)
        # width=1：固定请求宽度，长路径不撑宽右栏（显示区随列拉伸，超长截断）
        path_lbl = ctk.CTkLabel(path_frame, text="", fg_color="transparent",
                                anchor="w", width=1)
        path_lbl.pack(fill="x", expand=True, padx=8, pady=4)

        btn = ctk.CTkButton(frame, text=btn_text, width=_SELECT_BTN_W,
                            command=self._request_select_source)
        btn.grid(row=0, column=2, padx=(0, 0))
        self._controls.append(btn)

        # 固定宽度槽位：重置按钮显隐不引起选择按钮列移位
        # （子控件用 pack 放置，必须用 pack_propagate 锁定尺寸）
        slot = ctk.CTkFrame(frame, fg_color="transparent",
                            width=_RESET_SLOT_W, height=28)
        slot.grid(row=0, column=3)
        slot.pack_propagate(False)
        reset_btn = ctk.CTkButton(slot, text="↺", width=28,
                                  command=self._request_reset_source,
                                  fg_color="transparent",
                                  hover_color=("gray70", "gray40"),
                                  font=ctk.CTkFont(size=16))
        _ToolTip(reset_btn, "恢复默认")

        self._src_rows[key] = {"frame": path_frame, "label": path_lbl,
                               "reset": reset_btn}

    def _request_select_source(self) -> None:
        if self._on_select_source:
            self._on_select_source()

    def _request_reset_source(self) -> None:
        if self._on_reset_source:
            self._on_reset_source()

    def set_source_display(self, key: str, path: str, auto: bool) -> None:
        """更新指定视图（"python"/"generic"）锚点行的显示（app.py 推送）。"""
        row = self._src_rows.get(key)
        if not row:
            return
        color = ("gray60", "gray60") if auto else ("gray10", "gray90")
        row["label"].configure(text=path, text_color=color)
        row["frame"].configure(border_width=0)
        if auto:
            row["reset"].pack_forget()
        else:
            row["reset"].pack(side="left")

    # -- 执行目录（pre-build 的 cwd，默认插件目录） ----------------------

    def _update_exec_state(self) -> None:
        """执行目录行随 pre-build 命令有无联动启用/禁用（显示但置灰）。"""
        usable = self._enabled and bool(self._pre_build_var.get().strip())
        state = "normal" if usable else "disabled"
        self._exec_pick_btn.configure(state=state)
        self._exec_reset_btn.configure(state=state)

    def _refresh_exec_display(self) -> None:
        """刷新执行目录显示：未设置时以灰字展示默认回退（插件目录）。"""
        if self._exec_dir:
            text = Path(self._exec_dir).as_posix()
            color = ("gray10", "gray90")
            self._exec_reset_btn.pack(side="left")
        else:
            text = "插件目录（默认）"
            color = ("gray60", "gray60")
            self._exec_reset_btn.pack_forget()
        self._exec_dir_lbl.configure(text=text, text_color=color)

    def _pick_exec_dir(self) -> None:
        d = filedialog.askdirectory(title="选择预构建命令执行目录")
        if not d:
            return
        self._exec_dir = d
        self._refresh_exec_display()
        self._on_setting_changed()

    def _reset_exec_dir(self) -> None:
        self._exec_dir = ""
        self._refresh_exec_display()
        self._on_setting_changed()

    def get_exec_dir(self) -> str:
        """pre-build 执行目录绝对路径（空 = 未设置，构建时回退插件目录）。"""
        return self._exec_dir

    # -- Python 式视图（Python 系构建系统共用） -----------------------------

    def _build_python_view(self, view: ctk.CTkFrame) -> None:
        # uniform：强制 1:2 分栏比例，内容长短变化不移动分界
        view.grid_columnconfigure(0, weight=1, uniform="split")
        view.grid_columnconfigure(1, weight=2, uniform="split")
        view.grid_rowconfigure(0, weight=1)

        # ---- 左栏：依赖来源（只读检测面板） ----
        left = ctk.CTkFrame(view)
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="依赖来源",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 5))

        self._dep_manifest_label = ctk.CTkLabel(
            left, text="", anchor="w", justify="left", wraplength=280)
        self._dep_manifest_label.grid(row=1, column=0, sticky="w",
                                      padx=10, pady=(0, 5))

        ctk.CTkLabel(left,
                     text="依赖由项目自身的清单文件管理（Packer 不修改项目文件），"
                          "在右侧选择清单后构建时安装到 vendor/；项目根 = 清单"
                          "所在目录。未选择时跳过依赖打包，项目根 = 插件目录。"
                          "dghub-sdk 由右侧「包含 dghub-sdk」选项单独注入。",
                     font=ctk.CTkFont(size=11), text_color="gray",
                     wraplength=280, justify="left").grid(
            row=2, column=0, sticky="w", padx=10, pady=(5, 0))

        # 工具可用性标注（uv 需检测；pip 恒可用）
        self._tool_hint = ctk.CTkLabel(left, text="",
                                       font=ctk.CTkFont(size=11),
                                       text_color="gray", anchor="w",
                                       wraplength=280, justify="left")
        self._tool_hint.grid(row=3, column=0, sticky="w", padx=10,
                             pady=(10, 10))

        # ---- 右栏：源码目录 + entry + 构建选项 + 发布目标 ----
        right = ctk.CTkFrame(view)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        right.grid_columnconfigure(0, weight=1)

        # 依赖清单行（项目根锚点：uv/pip 各自记忆，未选 = 插件目录）
        self._build_source_row(right, row=0, key="python", label="依赖清单",
                               btn_text="选择文件")

        # entry 行
        entry_frame = ctk.CTkFrame(right, fg_color="transparent")
        entry_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(10, 5))
        entry_frame.grid_columnconfigure(1, weight=1)
        label_frame = ctk.CTkFrame(entry_frame, fg_color="transparent",
                                   width=_LABEL_W, height=28)
        label_frame.grid(row=0, column=0, padx=(0, 5), sticky="w")
        label_frame.pack_propagate(False)
        ctk.CTkLabel(label_frame, text="入口文件 ",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkLabel(label_frame, text="*", text_color="red",
                     font=ctk.CTkFont(size=14)).pack(side="left")
        self._entry_entry = ctk.CTkEntry(entry_frame, textvariable=self._entry_var)
        self._entry_entry.grid(row=0, column=1, sticky="ew", padx=5)
        self._controls.append(self._entry_entry)
        ctk.CTkLabel(entry_frame, text="相对于项目根（清单所在目录）",
                     font=ctk.CTkFont(size=11),
                     text_color="gray").grid(row=0, column=2, padx=(5, 0))

        # 构建选项
        opt_frame = ctk.CTkFrame(right, fg_color="transparent")
        opt_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        ctk.CTkLabel(opt_frame, text="构建选项",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(5, 5))

        self._build_exe_cb = ctk.CTkCheckBox(opt_frame, text="构建为独立 exe",
                                             variable=self._build_exe_var,
                                             command=self._on_build_exe_toggle)
        self._build_exe_cb.grid(row=1, column=0, sticky="w", pady=5)
        self._controls.append(self._build_exe_cb)

        # 工具依赖标注：勾选时后台预检 PyInstaller
        self._pyinstaller_hint = ctk.CTkLabel(
            opt_frame, text="需要 PyInstaller",
            font=ctk.CTkFont(size=11), text_color="gray")
        self._pyinstaller_hint.grid(row=1, column=1, sticky="w", padx=(5, 15))

        self._include_sdk_cb = ctk.CTkCheckBox(opt_frame, text="包含 dghub-sdk",
                                               variable=self._include_sdk_var)
        self._include_sdk_cb.grid(row=1, column=2, sticky="w", padx=(0, 10))
        self._controls.append(self._include_sdk_cb)

        # 发布目标
        self._build_target_section(right, row=3)

    # -- (无构建系统) 视图 ----------------------------------------------

    def _build_generic_view(self, view: ctk.CTkFrame) -> None:
        # uniform：强制 1:2 分栏比例，内容长短变化不移动分界
        view.grid_columnconfigure(0, weight=1, uniform="split")
        view.grid_columnconfigure(1, weight=2, uniform="split")
        view.grid_rowconfigure(1, weight=1)

        # 系统说明文案显示在顶部栏构建系统选择器右侧（app.py），此处不再重复

        # ---- 左栏：附加文件 / 规则清单 ----
        left = ctk.CTkFrame(view)
        left.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(left, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="附加文件",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w")
        self._add_rule_btn = ctk.CTkButton(header, text="添加规则", width=80,
                                           command=self._show_rule_input)
        self._add_rule_btn.grid(row=0, column=1, sticky="e", padx=(0, 5))
        self._add_file_btn = ctk.CTkButton(header, text="添加文件", width=80,
                                           command=self._add_extra_files)
        self._add_file_btn.grid(row=0, column=2, sticky="e")
        self._controls.extend([self._add_rule_btn, self._add_file_btn])

        ctk.CTkLabel(left,
                     text=".dll 默认放根目录，其他默认放 vendor/，可逐个修改；"
                          "规则（如 *.dll、dist/**）在构建时求值。",
                     font=ctk.CTkFont(size=11), text_color="gray",
                     wraplength=280, justify="left").grid(
            row=1, column=0, sticky="w", padx=10, pady=(0, 0))

        # 规则输入行（默认隐藏，「添加规则」时显示）
        self._rule_input = ctk.CTkFrame(left, fg_color="transparent")
        self._rule_input.grid(row=2, column=0, sticky="ew", padx=10, pady=(5, 0))
        self._rule_input.grid_columnconfigure(0, weight=1)
        self._rule_entry = ctk.CTkEntry(self._rule_input,
                                        placeholder_text="glob 规则，如 *.dll")
        self._rule_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self._rule_entry.bind("<Return>", lambda _: self._confirm_rule())
        self._rule_dest_menu = ctk.CTkOptionMenu(
            self._rule_input, width=90, values=list(_DEST_LABELS.values()))
        self._rule_dest_menu.set(_DEST_LABELS["vendor"])
        self._rule_dest_menu.grid(row=0, column=1, padx=(0, 5))
        ctk.CTkButton(self._rule_input, text="确认", width=50,
                      command=self._confirm_rule).grid(row=0, column=2,
                                                       padx=(0, 5))
        ctk.CTkButton(self._rule_input, text="取消", width=50,
                      fg_color="transparent",
                      hover_color=("gray70", "gray40"),
                      command=self._hide_rule_input).grid(row=0, column=3)
        self._rule_input.grid_remove()

        self._extra_list = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self._extra_list.grid(row=3, column=0, sticky="nsew", padx=5, pady=5)
        self._controls.append(self._extra_list)

        # ---- 右栏：预构建命令（含执行目录）+ 收集目录 + entry + 发布目标 ----
        # 行序遵循构建时序：先执行预构建，再从收集目录取产物
        right = ctk.CTkFrame(view)
        right.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=10)
        right.grid_columnconfigure(0, weight=1)

        # 预构建命令行
        pb_frame = ctk.CTkFrame(right, fg_color="transparent")
        pb_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        pb_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(pb_frame, text="预构建命令", width=_LABEL_W, anchor="w",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=(0, 5), sticky="w")
        self._pre_build_entry = ctk.CTkEntry(
            pb_frame, textvariable=self._pre_build_var,
            placeholder_text="可选，如 dotnet build -c Release，构建前在执行目录执行")
        self._pre_build_entry.grid(row=0, column=1, sticky="ew", padx=5)
        self._controls.append(self._pre_build_entry)
        # 尾部等宽占位：本行无选择按钮，占位使输入区右边界与下方目录行一致
        ctk.CTkFrame(pb_frame, fg_color="transparent",
                     width=_SELECT_BTN_W, height=28).grid(row=0, column=2)
        ctk.CTkFrame(pb_frame, fg_color="transparent",
                     width=_RESET_SLOT_W, height=28).grid(row=0, column=3)

        # 执行目录行（预构建命令的 cwd；仅填写了命令时可用，默认插件目录）
        ex_frame = ctk.CTkFrame(right, fg_color="transparent")
        ex_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(10, 0))
        ex_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(ex_frame, text="执行目录", width=_LABEL_W, anchor="w",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=(0, 5), sticky="w")
        exec_path_frame = ctk.CTkFrame(ex_frame, fg_color=("gray85", "gray25"),
                                       border_width=0, corner_radius=6)
        exec_path_frame.grid(row=0, column=1, sticky="ew", padx=5)
        self._exec_dir_lbl = ctk.CTkLabel(exec_path_frame, text="",
                                          fg_color="transparent",
                                          anchor="w", width=1)
        self._exec_dir_lbl.pack(fill="x", expand=True, padx=8, pady=4)
        self._exec_pick_btn = ctk.CTkButton(ex_frame, text="选择目录",
                                            width=_SELECT_BTN_W,
                                            command=self._pick_exec_dir)
        self._exec_pick_btn.grid(row=0, column=2)
        # 固定宽度槽位：重置按钮显隐不引起选择按钮列移位
        exec_slot = ctk.CTkFrame(ex_frame, fg_color="transparent",
                                 width=_RESET_SLOT_W, height=28)
        exec_slot.grid(row=0, column=3)
        exec_slot.pack_propagate(False)
        self._exec_reset_btn = ctk.CTkButton(
            exec_slot, text="↺", width=28, command=self._reset_exec_dir,
            fg_color="transparent", hover_color=("gray70", "gray40"),
            font=ctk.CTkFont(size=16))
        _ToolTip(self._exec_reset_btn, "恢复默认")
        self._refresh_exec_display()

        # 收集目录行（原始文件选取根：entry / 附加文件 / glob 均相对此目录）
        self._build_source_row(right, row=2, key="generic", label="收集目录")

        # entry 行（可编辑 + 选择器辅助：pre-build 生成物可手工输入）
        entry_frame = ctk.CTkFrame(right, fg_color="transparent")
        entry_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(10, 5))
        entry_frame.grid_columnconfigure(1, weight=1)
        label_frame = ctk.CTkFrame(entry_frame, fg_color="transparent",
                                   width=_LABEL_W, height=28)
        label_frame.grid(row=0, column=0, padx=(0, 5), sticky="w")
        label_frame.pack_propagate(False)
        ctk.CTkLabel(label_frame, text="入口文件 ",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkLabel(label_frame, text="*", text_color="red",
                     font=ctk.CTkFont(size=14)).pack(side="left")
        self._entry_generic_entry = ctk.CTkEntry(
            entry_frame, textvariable=self._entry_generic_var,
            placeholder_text="相对收集目录，可为预构建生成物")
        self._entry_generic_entry.grid(row=0, column=1, sticky="ew", padx=5)
        self._controls.append(self._entry_generic_entry)
        self._pick_entry_btn = ctk.CTkButton(entry_frame, text="选择文件",
                                             width=_SELECT_BTN_W,
                                             command=self._pick_generic_entry)
        self._pick_entry_btn.grid(row=0, column=2, padx=(0, 0))
        self._controls.append(self._pick_entry_btn)
        # 尾部等宽占位：与目录行的重置槽位对齐，使选择按钮列一致
        ctk.CTkFrame(entry_frame, fg_color="transparent",
                     width=_RESET_SLOT_W, height=28).grid(row=0, column=3)

        self._generic_hint = ctk.CTkLabel(right, text="",
                                          font=ctk.CTkFont(size=11),
                                          text_color="#FF4444")
        self._generic_hint.grid(row=4, column=0, sticky="w", padx=10)

        # 发布目标
        self._build_target_section(right, row=5)

    # -- 共享分区 -------------------------------------------------------

    def _build_target_section(self, parent: ctk.CTkFrame, row: int) -> None:
        """发布目标单选组：两视图各自渲染，共享同一 _target_var。"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=10, pady=5)
        ctk.CTkLabel(frame, text="发布目标",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", pady=(5, 5))
        for text, val in [("文件夹（本地调试）", "folder"),
                          ("zip 包（分发）", "zip")]:
            rb = ctk.CTkRadioButton(frame, text=text,
                                    variable=self._target_var, value=val)
            rb.pack(anchor="w", padx=10, pady=2)
            self._controls.append(rb)

    def _build_preview(self, parent: ctk.CTkFrame) -> None:
        preview_frame = ctk.CTkFrame(parent)
        preview_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        preview_frame.grid_rowconfigure(1, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(preview_frame, text="输出文件预览",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 5))

        self._preview = ctk.CTkTextbox(preview_frame, wrap="word",
                                       font=("Consolas", 11), state="disabled")
        self._preview.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self._controls.append(self._preview)

    # ------------------------------------------------------------------
    # 构建系统切换
    # ------------------------------------------------------------------

    def set_build_system(self, bs_id: str) -> None:
        """整帧切换视图并加载该系统的命名空间配置。"""
        self._bs = bs_id
        if bs_id == "generic":
            self._python_view.grid_remove()
            self._generic_view.grid()
        else:
            self._generic_view.grid_remove()
            self._python_view.grid()
            # uv/pip 各自的 entry / 构建选项（受 loading 保护防反馈）
            if self._pm:
                cfg = self._pm.get_bs_config(bs_id)
                self._loading = True
                try:
                    self._entry_var.set(cfg.get("entry", "main.py"))
                    self._build_exe_var.set(cfg.get("build_exe", True))
                    self._include_sdk_var.set(cfg.get("include_sdk", True))
                finally:
                    self._loading = False
            self._update_dep_source()
        self._refresh_preview()

    def get_build_system(self) -> str:
        return self._bs

    def set_source_dir(self, d: str) -> None:
        """由 app.py 推送当前系统的项目根/收集目录，文件选择器/规则求值以此为界。"""
        self._source_dir = d
        if self._bs == "generic":
            self._refresh_extra_list()

    def set_manifest(self, path: str) -> None:
        """由 app.py 推送当前系统选定的依赖清单（绝对路径，空 = 未选）。"""
        self._manifest_path = path
        if self._bs != "generic":
            self._update_dep_source()

    def get_manifest(self) -> str:
        """返回当前系统选定的依赖清单绝对路径（空 = 未选）。"""
        if self._bs == "generic":
            return ""
        return self._manifest_path

    def set_entry(self, entry: str) -> None:
        """设置 Python 系视图的入口（[tool.dghub] 自动填充用，走正常持久化）。"""
        self._entry_var.set(entry)

    # ------------------------------------------------------------------
    # 依赖来源面板（Python 系构建系统）
    # ------------------------------------------------------------------

    def _update_dep_source(self) -> None:
        """刷新选定清单的显示与工具可用性标注。"""
        bs = BUILD_SYSTEMS.get(self._bs)
        if bs is None or not bs.dep_manifest_hint:
            return
        if self._manifest_path:
            name = Path(self._manifest_path).name
            if bs.is_known_manifest(name):
                self._dep_manifest_label.configure(
                    text=f"✓ {name}", text_color="green")
            else:
                # 浅红警示：所选文件不是本系统可识别的清单类型
                self._dep_manifest_label.configure(
                    text=f"? {name} 未知构建系统",
                    text_color=("#C0504D", "#E57373"))
        else:
            # 黄色提示：未选清单可构建，但会跳过依赖打包
            self._dep_manifest_label.configure(
                text=f"未选择（{bs.dep_manifest_hint}）— 将跳过依赖打包",
                text_color=("#9A6700", "#E0B040"))
        # 工具可用性后台预检
        threading.Thread(target=self._check_tool_bg, args=(self._bs,),
                         daemon=True).start()

    def _check_tool_bg(self, bs_id: str) -> None:
        bs = BUILD_SYSTEMS.get(bs_id)
        if bs is None:
            return
        ok, text = bs.check_available()
        color = "gray" if ok else "#FF4444"
        try:
            self.after(0, lambda: self._tool_hint.configure(
                text=text, text_color=color))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 附加文件 / 规则管理（(无构建系统)）
    # ------------------------------------------------------------------

    def _rel_to_source(self, path: str) -> Optional[str]:
        """将绝对路径转为相对收集目录的路径；不在收集目录内返回 None。"""
        src = self._source_dir or self._plugin_dir
        if not src:
            return None
        try:
            return Path(path).resolve().relative_to(
                Path(src).resolve()).as_posix()
        except ValueError:
            return None

    def _pick_generic_entry(self) -> None:
        src = self._source_dir or self._plugin_dir
        f = filedialog.askopenfilename(title="选择入口文件", initialdir=src)
        if not f:
            return
        rel = self._rel_to_source(f)
        if rel is None:
            self._generic_hint.configure(text="入口文件必须位于收集目录内")
            return
        self._generic_hint.configure(text="")
        self._entry_generic_var.set(rel)
        # entry 不允许同时出现在附加文件清单
        self._extra_files = [e for e in self._extra_files
                             if e.get("path") != rel]
        self._refresh_extra_list()
        self._auto_save_extra_files()

    def _add_extra_files(self) -> None:
        src = self._source_dir or self._plugin_dir
        files = filedialog.askopenfilenames(title="选择产物文件", initialdir=src)
        if not files:
            return
        rejected = False
        entry_rel = self._entry_generic_var.get()
        existing = {e["path"] for e in self._extra_files if "path" in e}
        for f in files:
            rel = self._rel_to_source(f)
            if rel is None:
                rejected = True
                continue
            if rel in existing or rel == entry_rel:
                continue
            # .dll 默认根目录（与 exe 同级），其他默认 vendor/
            dest = "root" if rel.lower().endswith(".dll") else "vendor"
            self._extra_files.append({"path": rel, "dest": dest})
            existing.add(rel)
        self._generic_hint.configure(
            text="已跳过收集目录外的文件" if rejected else "")
        self._refresh_extra_list()
        self._auto_save_extra_files()

    def _show_rule_input(self) -> None:
        self._rule_input.grid()
        self._rule_entry.focus_set()

    def _hide_rule_input(self) -> None:
        self._rule_entry.delete(0, "end")
        self._rule_input.grid_remove()

    def _confirm_rule(self) -> None:
        pattern = self._rule_entry.get().strip()
        if not pattern:
            return
        existing = {e["pattern"] for e in self._extra_files if "pattern" in e}
        if pattern not in existing:
            dest = _DEST_VALUES.get(self._rule_dest_menu.get(), "vendor")
            self._extra_files.append({"pattern": pattern, "dest": dest})
            self._refresh_extra_list()
            self._auto_save_extra_files()
        self._hide_rule_input()

    def _remove_extra_file(self, idx: int) -> None:
        if 0 <= idx < len(self._extra_files):
            self._extra_files.pop(idx)
            self._refresh_extra_list()
            self._auto_save_extra_files()

    def _set_extra_dest(self, idx: int, label: str) -> None:
        if 0 <= idx < len(self._extra_files):
            self._extra_files[idx]["dest"] = _DEST_VALUES.get(label, "vendor")
            self._auto_save_extra_files()
            self._refresh_preview()

    def _refresh_extra_list(self) -> None:
        for w in self._extra_list.winfo_children():
            w.destroy()

        workdir = self._source_dir or self._plugin_dir
        for i, item in enumerate(self._extra_files):
            row = ctk.CTkFrame(self._extra_list, fg_color="transparent")
            row.pack(fill="x", padx=2, pady=1)

            is_rule = "pattern" in item
            text = item["pattern"] if is_rule else item["path"]
            if is_rule:
                ctk.CTkLabel(row, text="规则", width=34,
                             font=ctk.CTkFont(size=10),
                             fg_color=("gray75", "gray35"),
                             corner_radius=4).pack(side="left", padx=(0, 5))
            ctk.CTkLabel(row, text=text, anchor="w").pack(
                side="left", fill="x", expand=True)

            ctk.CTkButton(row, text="×", width=24, height=22,
                          fg_color="transparent", hover_color="#FF4444",
                          font=ctk.CTkFont(size=14),
                          command=lambda i=i: self._remove_extra_file(i)).pack(
                side="right")
            menu = ctk.CTkOptionMenu(
                row, width=90, values=list(_DEST_LABELS.values()),
                command=lambda label, i=i: self._set_extra_dest(i, label))
            menu.set(_DEST_LABELS[item["dest"]])
            menu.pack(side="right", padx=(5, 5))

            if is_rule and workdir:
                n = len(evaluate_pattern(Path(workdir), item["pattern"]))
                hint = (f"匹配 {n} 个文件" if n else
                        "当前无匹配，构建时（pre-build 后）求值")
                ctk.CTkLabel(self._extra_list, text=f"    {hint}",
                             font=ctk.CTkFont(size=10), text_color="gray",
                             anchor="w").pack(fill="x", padx=2)

    def _auto_save_extra_files(self) -> None:
        if self._pm:
            self._pm.write_extra_files(self._extra_files)
        self._refresh_preview()

    def get_extra_files(self) -> list[dict[str, str]]:
        """Return extra entries: [{"path"|"pattern", "dest"}]."""
        return list(self._extra_files)

    # ------------------------------------------------------------------
    # PyInstaller 预检标注
    # ------------------------------------------------------------------

    def _on_build_exe_toggle(self) -> None:
        self._refresh_preview()
        if self._build_exe_var.get():
            threading.Thread(target=self._check_pyinstaller_bg,
                             daemon=True).start()

    def _check_pyinstaller_bg(self) -> None:
        """后台预检 PyInstaller，仅更新标注文案，不阻断构建。"""
        try:
            result = subprocess.run(
                _get_python_exe() + ["-m", "PyInstaller", "--version"],
                capture_output=True, text=True, timeout=30,
                creationflags=_NO_WINDOW)
            ok = result.returncode == 0
        except Exception:
            ok = False
        if ok:
            text, color = "需要 PyInstaller", "gray"
        else:
            text, color = "未检测到 PyInstaller，请 pip install pyinstaller", "#FF4444"
        try:
            self.after(0, lambda: self._pyinstaller_hint.configure(
                text=text, text_color=color))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # persistence（按构建系统命名空间读写 project.json）
    # ------------------------------------------------------------------

    def _on_setting_changed(self, *args: Any) -> None:
        """Persist settings on any control change (skips restore phase)."""
        if self._loading:
            return
        self.save_settings()

    def set_plugin_dir(self, d: str, pm: Optional[ProjectManager] = None) -> None:
        if pm:
            self._pm = pm
        self._plugin_dir = d
        self._set_enabled(True)
        if self._pm:
            # Load saved settings (suppress autosave during restore)
            self._loading = True
            try:
                project = self._pm.read_project()
                gen = project["build_systems"]["generic"]
                self._entry_generic_var.set(gen.get("entry", ""))
                self._pre_build_var.set(gen.get("pre_build", ""))
                rel_exec = gen.get("exec_dir", "")
                self._exec_dir = (self._pm.to_absolute(rel_exec)
                                  if rel_exec else "")
                self._refresh_exec_display()
                self._extra_files = list(gen.get("extra_files", []))
                self._target_var.set(project.get("target", "zip"))
                # uv/pip 的字段由 set_build_system 按当前系统加载
            finally:
                self._loading = False
            self._refresh_extra_list()
        self._refresh_preview()

    def save_settings(self) -> None:
        """Save current distribute settings to project config."""
        if not self._pm:
            return
        # read-then-merge：保留顶层与其他命名空间（含未知系统）已有键
        data = self._pm.read_project()
        data["target"] = self._target_var.get()
        cfg = data["build_systems"].setdefault(self._bs, {})
        if self._bs == "generic":
            cfg["entry"] = self._entry_generic_var.get()
            cfg["pre_build"] = self._pre_build_var.get()
            cfg["exec_dir"] = (self._pm.to_relative(self._exec_dir)
                               if self._exec_dir else "")
        else:
            cfg["entry"] = self._entry_var.get()
            cfg["build_exe"] = self._build_exe_var.get()
            cfg["include_sdk"] = self._include_sdk_var.get()
        self._pm.write_project(data)

    # ------------------------------------------------------------------
    # preview
    # ------------------------------------------------------------------

    def refresh_preview(self, output_dir: str = "") -> None:
        """Update the file tree preview. Called from app.py."""
        self._refresh_preview(output_dir)

    def _refresh_preview(self, out_dir: str = "") -> None:
        plugin_name = Path(self._plugin_dir).name if self._plugin_dir else "插件名"
        lines: list[str] = []
        lines.append(f"{'='*30}")
        lines.append(f"输出目录: {out_dir or f'（默认 {plugin_name}/output/）'}")

        if self._bs == "generic":
            self._render_generic_preview(lines, plugin_name)
        else:
            self._render_python_preview(lines, plugin_name)

        self._preview.configure(state="normal")
        self._preview.delete("1.0", "end")
        self._preview.insert("1.0", "\n".join(lines))
        self._preview.configure(state="disabled")

    def _render_python_preview(self, lines: list[str], plugin_name: str) -> None:
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

    def _render_generic_preview(self, lines: list[str], plugin_name: str) -> None:
        entry = self._entry_generic_var.get() or "（未选择入口文件）"
        workdir = self._source_dir or self._plugin_dir

        def _expand(dest: str) -> list[str]:
            """展开该目标位置的精确条目与规则匹配（规则每条最多列 10 个）。"""
            out: list[str] = []
            for e in self._extra_files:
                if e["dest"] != dest:
                    continue
                if "path" in e:
                    out.append(Path(e["path"]).name)
                elif workdir:
                    matched = evaluate_pattern(Path(workdir), e["pattern"])
                    out.extend(Path(m).name for m in matched[:10])
                    if len(matched) > 10:
                        out.append(f"…共 {len(matched)} 个（{e['pattern']}）")
                    elif not matched:
                        out.append(f"（{e['pattern']} 构建时求值）")
            return out

        target = self._target_var.get()
        if target == "zip":
            lines.append(f"  {plugin_name}.zip  ← 分发包")
        else:
            lines.append(f"  dev/{plugin_name}/")
        lines.append(f"    ├── manifest.json")
        lines.append(f"    ├── {entry}  ← entry")
        for name in _expand("root"):
            lines.append(f"    ├── {name}")
        vendor_names = _expand("vendor")
        if vendor_names:
            lines.append(f"    └── vendor/")
            for name in vendor_names:
                lines.append(f"        ├── {name}")

    # ------------------------------------------------------------------
    # accessors for build pipeline
    # ------------------------------------------------------------------

    def get_entry(self) -> str:
        if self._bs == "generic":
            return self._entry_generic_var.get().strip()
        return self._entry_var.get().strip()

    def get_pre_build(self) -> str:
        return self._pre_build_var.get()

    def get_build_exe(self) -> bool:
        # exe 构建为 Python 系（uv/pip）专属能力
        if self._bs == "generic":
            return False
        return self._build_exe_var.get()

    def get_include_sdk(self) -> bool:
        if self._bs == "generic":
            return False
        return self._include_sdk_var.get()

    def get_target(self) -> str:
        return self._target_var.get()

    def clear_entry_error(self) -> None:
        """Reset entry field border after source dir change."""
        self._entry_entry.configure(border_width=0)
        self._entry_generic_entry.configure(border_width=0)
