"""Build tab — 打包内容与发布选项（纯 GUI 工具的单视图构建页）。

- 项目根 / 入口文件（阶段 1 输入）
- 打包内容：统一文件选择列表（文件 / 目录 / 规则三种条目，标签标记入口）
  +「添加文件」（混合选择对话框）/「添加规则」/「从预构建填充」按钮
- 发布选项：No Zip 复选框 + 预览树（输出目录在顶部栏）
"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any, Callable, Optional

import customtkinter as ctk

from backend.builder import Builder, evaluate_pattern
from backend.project_manager import ProjectManager

# 右栏各行统一的前导标签宽度（像素）
_LABEL_W = 92

# 条目类型标签（列表显示）
_KIND_LABELS = {"path": "文件", "dir": "目录", "pattern": "规则"}


class _PickerDialog(ctk.CTkToplevel):
    """文件 + 目录混合选择对话框（ttk.Treeview 懒加载浏览项目根）。

    文件与文件夹均可多选；确认后经 on_pick 回调相对项目根的路径列表
    [("path"/"dir", rel), ...]。
    """

    def __init__(self, master: Any, root_dir: Path,
                 on_pick: Callable[[list[tuple[str, str]]], None]) -> None:
        super().__init__(master)
        self.title("选择打包内容")
        self.geometry("560x460")
        self.minsize(420, 320)
        self._root = root_dir
        self._on_pick = on_pick
        self._selected: list[tuple[str, str]] = []

        self._tree = ttk.Treeview(self, selectmode="extended",
                                  columns=("kind",), show="tree headings")
        self._tree.heading("#0", text="项目根")
        self._tree.heading("kind", text="类型")
        self._tree.column("kind", width=70, stretch=False)
        self._tree.pack(fill="both", expand=True, padx=10, pady=(10, 5))
        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<Button-3>", self._on_right_click)

        self._sel_label = ctk.CTkLabel(self, text="已选 0 项",
                                       anchor="w", font=ctk.CTkFont(size=12))
        self._sel_label.pack(fill="x", padx=10)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(btns, text="取消", width=80,
                      command=self.destroy).pack(side="right")
        ctk.CTkButton(btns, text="添加", width=80,
                      command=self._confirm).pack(side="right", padx=5)

        # 填充根目录一级
        self._populate("", self._root)
        self._tree.item("", open=True)
        self.after(100, self._sync_label)

    # -- 目录树懒加载 --

    def _populate(self, iid: str, path: Path) -> None:
        try:
            entries = sorted(path.iterdir(),
                             key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return
        for p in entries:
            kind = "dir" if p.is_dir() else "file"
            child = self._tree.insert(
                iid, "end", text=p.name,
                values=("目录" if kind == "dir" else "文件",))
            if kind == "dir":
                # 预插占位子节点，展开时填充（懒加载）
                self._tree.insert(child, "end", text="")
            self._tree.item(child, tags=(kind,))

    def _on_double_click(self, event: Any) -> None:
        iid = self._tree.identify_row(event.y)
        if not iid:
            return
        if self._tree.item(iid, "tags") == ("dir",):
            if self._tree.get_children(iid) == ():
                return
            # 展开时填充真实子节点（移除占位）
            self._fill_children(iid)

    def _fill_children(self, iid: str) -> None:
        # 移除占位符
        for child in self._tree.get_children(iid):
            if self._tree.item(child, "text") == "":
                self._tree.delete(child)
        path = self._path_of(iid)
        if path is not None:
            self._populate(iid, path)

    def _on_right_click(self, event: Any) -> None:
        iid = self._tree.identify_row(event.y)
        if not iid:
            return
        self._tree.selection_set(iid)
        if self._tree.item(iid, "tags") == ("dir",):
            self._fill_children(iid)

    def _path_of(self, iid: str) -> Optional[Path]:
        """由节点 iid 解析绝对路径（根为空串 iid）。"""
        if iid == "":
            return self._root
        parts: list[str] = []
        cur: Any = iid
        while cur != "":
            parts.insert(0, self._tree.item(cur, "text"))
            cur = self._tree.parent(cur)
        return self._root.joinpath(*parts)

    # -- 选中收集 --

    def _sync_label(self) -> None:
        n = len(self._selected)
        self._sel_label.configure(text=f"已选 {n} 项")

    def _confirm(self) -> None:
        picked: list[tuple[str, str]] = []
        seen: set[str] = set()
        for iid in self._tree.selection():
            path = self._path_of(iid)
            if path is None:
                continue
            try:
                rel = path.relative_to(self._root).as_posix()
            except ValueError:
                continue
            if rel in seen:
                continue
            seen.add(rel)
            kind = "dir" if path.is_dir() else "path"
            picked.append((kind, rel))
        if not picked:
            return
        self._on_pick(picked)
        self.destroy()


class DistributeTab(ctk.CTkFrame):
    """构建页：项目根 / 入口 / 打包内容 / 发布选项 / 预览。"""

    def __init__(self, master: Any,
                 on_select_source: Optional[Callable[[], None]] = None,
                 on_reset_source: Optional[Callable[[], None]] = None,
                 on_entry_edit: Optional[Callable[[], None]] = None,
                 on_fill_builder: Optional[Callable[[], None]] = None,
                 **kwargs: Any) -> None:
        super().__init__(master, **kwargs)
        self._pm: Optional[ProjectManager] = None
        self._plugin_dir: Optional[str] = None
        self._source_dir: Optional[str] = None
        self._loading = False
        self._enabled = False
        self._on_select_source = on_select_source
        self._on_reset_source = on_reset_source
        self._on_entry_edit = on_entry_edit
        self._on_fill_builder = on_fill_builder
        self._controls: list[ctk.CTkBaseClass] = []

        self._entry_var = ctk.StringVar(value="")
        self._no_zip_var = ctk.BooleanVar(value=False)

        self._build_ui()
        self._set_enabled(False)

    def _set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        state = "normal" if enabled else "disabled"
        for w in self._controls:
            try:
                w.configure(state=state)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        # ---- 左栏：项目根 + 入口 + 打包内容 ----
        left = ctk.CTkFrame(self)
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left.grid_columnconfigure(1, weight=1)

        # 项目根行
        ctk.CTkLabel(left, text="项目根", width=_LABEL_W, anchor="w",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=(10, 5), pady=(10, 0), sticky="w")
        root_frame = ctk.CTkFrame(left, fg_color=("gray85", "gray25"),
                                  border_width=0, corner_radius=6)
        root_frame.grid(row=0, column=1, sticky="ew", padx=5, pady=(10, 0))
        self._root_lbl = ctk.CTkLabel(root_frame, text="", fg_color="transparent",
                                      anchor="w", width=1)
        self._root_lbl.pack(fill="x", expand=True, padx=8, pady=4)
        btn = ctk.CTkButton(left, text="选择目录", width=90,
                            command=self._request_select_source)
        btn.grid(row=0, column=2, padx=(5, 0), pady=(10, 0))
        self._root_reset = ctk.CTkButton(
            left, text="↺", width=28, command=self._request_reset_source,
            fg_color="transparent", hover_color=("gray70", "gray40"),
            font=ctk.CTkFont(size=16))
        self._root_reset.grid(row=0, column=3, padx=(2, 10), pady=(10, 0))
        self._controls.extend([btn, self._root_reset])

        # 入口文件行（阶段 1 输入）
        ctk.CTkLabel(left, text="入口文件 ", width=_LABEL_W, anchor="w",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=0, padx=(10, 5), pady=(12, 0), sticky="w")
        ctk.CTkLabel(left, text="*", text_color="red",
                     font=ctk.CTkFont(size=14)).grid(
            row=1, column=0, padx=(0, 0), pady=(12, 0), sticky="e")
        self._entry_entry = ctk.CTkEntry(
            left, textvariable=self._entry_var,
            placeholder_text="相对项目根（Python 预构建为 .py 源码入口）")
        self._entry_entry.grid(row=1, column=1, sticky="ew", padx=5,
                               pady=(12, 0))
        self._controls.append(self._entry_entry)

        # 打包内容
        ctk.CTkLabel(left, text="打包内容", width=_LABEL_W, anchor="w",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=2, column=0, padx=10, pady=(16, 5), sticky="w")
        add_btn = ctk.CTkButton(left, text="添加", width=70,
                                command=self._add_items)
        add_btn.grid(row=2, column=1, sticky="w", padx=(5, 0), pady=(16, 5))
        rule_btn = ctk.CTkButton(left, text="添加规则", width=90,
                                 command=self._show_rule_input)
        rule_btn.grid(row=2, column=1, sticky="e", padx=(0, 5), pady=(16, 5))
        fill_btn = ctk.CTkButton(
            left, text="从预构建填充", width=110,
            command=self._fill_builder_clicked)
        fill_btn.grid(row=2, column=2, columnspan=2, sticky="w",
                      padx=(5, 10), pady=(16, 5))
        self._controls.extend([add_btn, rule_btn, fill_btn])

        # 规则输入行（默认隐藏）
        self._rule_input = ctk.CTkFrame(left, fg_color="transparent")
        self._rule_input.grid(row=3, column=1, columnspan=3, sticky="ew",
                              padx=5, pady=(0, 5))
        self._rule_input.grid_columnconfigure(0, weight=1)
        self._rule_entry = ctk.CTkEntry(self._rule_input,
                                        placeholder_text="glob 规则，如 dist/**")
        self._rule_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self._rule_entry.bind("<Return>", lambda _: self._confirm_rule())
        ctk.CTkButton(self._rule_input, text="确认", width=50,
                      command=self._confirm_rule).grid(row=0, column=1,
                                                       padx=(0, 5))
        ctk.CTkButton(self._rule_input, text="取消", width=50,
                      fg_color="transparent",
                      hover_color=("gray70", "gray40"),
                      command=self._hide_rule_input).grid(row=0, column=2)
        self._rule_input.grid_remove()

        # 条目列表
        self._item_list = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self._item_list.grid(row=4, column=0, columnspan=4, sticky="nsew",
                             padx=5, pady=5)
        left.grid_rowconfigure(4, weight=1)
        self._controls.append(self._item_list)

        # ---- 右栏：发布选项 + 预览 ----
        right = ctk.CTkFrame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(right, text="发布选项",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 5))
        self._no_zip_cb = ctk.CTkCheckBox(
            right, text="No Zip（输出文件夹模式，勾选 = 本地调试）",
            variable=self._no_zip_var, command=self._on_no_zip_changed)
        self._no_zip_cb.grid(row=1, column=0, sticky="w", padx=10, pady=2)
        self._controls.append(self._no_zip_cb)

        # 输出文件预览
        ctk.CTkLabel(right, text="输出文件预览",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=2, column=0, sticky="nw", padx=10, pady=(10, 5))
        self._preview = ctk.CTkTextbox(right, wrap="word",
                                       font=("Consolas", 11),
                                       state="disabled")
        self._preview.grid(row=3, column=0, sticky="nsew", padx=10,
                           pady=(0, 10))
        self._controls.append(self._preview)

        # 变更即保存
        self._entry_var.trace_add("write", self._on_setting_changed)
        self._entry_var.trace_add("write", self._on_entry_error_edit)
        self._no_zip_var.trace_add("write", self._on_setting_changed)

    # ------------------------------------------------------------------
    # 项目根行
    # ------------------------------------------------------------------

    def _request_select_source(self) -> None:
        if self._on_select_source:
            self._on_select_source()

    def _request_reset_source(self) -> None:
        if self._on_reset_source:
            self._on_reset_source()

    def set_source_display(self, path: str, auto: bool) -> None:
        """由 app.py 推送项目根显示（auto = 回退插件目录）。"""
        color = ("gray60", "gray60") if auto else ("gray10", "gray90")
        self._root_lbl.configure(text=path, text_color=color)
        if auto:
            self._root_reset.grid_remove()
        else:
            self._root_reset.grid()

    # ------------------------------------------------------------------
    # 打包内容（统一文件列表，标签标记入口）
    # ------------------------------------------------------------------

    def _builder(self) -> Optional[Builder]:
        return Builder(self._pm) if self._pm else None

    def _add_items(self) -> None:
        if not self._plugin_dir:
            return
        _PickerDialog(self, Path(self._source_dir or self._plugin_dir),
                      self._on_picked)

    def _on_picked(self, picked: list[tuple[str, str]]) -> None:
        b = self._builder()
        if b is None:
            return
        for kind, rel in picked:
            if kind == "dir":
                b.add_dir(rel)
            else:
                b.add_file(rel)
        self._refresh_item_list()
        self._refresh_preview()

    def _show_rule_input(self) -> None:
        self._rule_input.grid()
        self._rule_entry.focus_set()

    def _hide_rule_input(self) -> None:
        self._rule_entry.delete(0, "end")
        self._rule_input.grid_remove()

    def _confirm_rule(self) -> None:
        pattern = self._rule_entry.get().strip()
        if pattern:
            b = self._builder()
            if b is not None:
                b.add_rule(pattern)
                self._refresh_item_list()
                self._refresh_preview()
        self._hide_rule_input()

    def _fill_builder_clicked(self) -> None:
        if self._on_fill_builder:
            self._on_fill_builder()

    def _refresh_item_list(self) -> None:
        for w in self._item_list.winfo_children():
            w.destroy()
        b = self._builder()
        if b is None:
            return
        workdir = Path(self._source_dir or self._plugin_dir or ".")
        for i, item in enumerate(b.items()):
            kind = ("path" if "path" in item
                    else ("dir" if "dir" in item else "pattern"))
            rel = item.get(kind, "")
            tags = item.get("tags", [])
            is_entry = "entry" in tags

            row = ctk.CTkFrame(self._item_list, fg_color="transparent")
            row.pack(fill="x", padx=2, pady=1)

            ctk.CTkLabel(row, text=_KIND_LABELS.get(kind, kind), width=34,
                         font=ctk.CTkFont(size=10),
                         fg_color=("gray75", "gray35"),
                         corner_radius=4).pack(side="left", padx=(0, 5))
            if is_entry:
                ctk.CTkLabel(row, text="入口", width=34,
                             font=ctk.CTkFont(size=10),
                             fg_color=("#4CAF50", "#2E7D32"),
                             corner_radius=4).pack(side="left", padx=(0, 5))
            ctk.CTkLabel(row, text=rel, anchor="w").pack(
                side="left", fill="x", expand=True)

            if kind == "pattern" and workdir.is_dir():
                n = len(evaluate_pattern(workdir, rel))
                hint = (f"匹配 {n} 个文件" if n else
                        "当前无匹配，构建时求值")
                ctk.CTkLabel(self._item_list, text=f"    {hint}",
                             font=ctk.CTkFont(size=10), text_color="gray",
                             anchor="w").pack(fill="x", padx=2)

            if not is_entry and kind == "path":
                ctk.CTkButton(row, text="设为入口", width=70, height=22,
                              font=ctk.CTkFont(size=10),
                              command=lambda i=i: self._set_entry(i)).pack(
                    side="right", padx=(5, 2))
            ctk.CTkButton(row, text="×", width=24, height=22,
                          fg_color="transparent", hover_color="#FF4444",
                          font=ctk.CTkFont(size=14),
                          command=lambda i=i: self._remove_item(i)).pack(
                side="right")

    def _set_entry(self, idx: int) -> None:
        b = self._builder()
        if b is None:
            return
        # 清除其他条目的 entry 标签，再贴到目标条目
        for i, item in enumerate(b.items()):
            if i == idx:
                continue
            if "entry" in item.get("tags", []):
                b.set_tags(i, [t for t in item.get("tags", [])
                               if t != "entry"])
        tags = list(b.items()[idx].get("tags", []))
        if "entry" not in tags:
            tags.append("entry")
        b.set_tags(idx, tags)
        self._refresh_item_list()
        self._refresh_preview()

    def _remove_item(self, idx: int) -> None:
        b = self._builder()
        if b is not None:
            b.remove_item(idx)
            self._refresh_item_list()
            self._refresh_preview()

    def get_builder(self) -> Optional[Builder]:
        return self._builder()

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _on_setting_changed(self, *args: Any) -> None:
        if self._loading:
            return
        self.save_settings()
        self._refresh_preview()

    def _on_entry_error_edit(self, *args: Any) -> None:
        if self._loading:
            return
        self.clear_entry_error()
        if self._on_entry_edit:
            self._on_entry_edit()

    def _on_no_zip_changed(self) -> None:
        self._refresh_preview()

    def set_plugin_dir(self, d: str, pm: Optional[ProjectManager] = None) -> None:
        if pm:
            self._pm = pm
        self._plugin_dir = d
        self._set_enabled(True)
        if self._pm:
            self._loading = True
            try:
                project = self._pm.read_project()
                self._entry_var.set(project.get("entry", ""))
                self._no_zip_var.set(
                    bool(project.get("builder", {}).get("no_zip", False)))
            finally:
                self._loading = False
            self._refresh_item_list()
        self._refresh_preview()

    def save_settings(self) -> None:
        """保存入口（顶层）与 No Zip（builder 节）到 project.json。"""
        if not self._pm:
            return
        project = self._pm.read_project()
        project["entry"] = self._entry_var.get()
        builder = dict(project.get("builder", {}))
        builder["no_zip"] = self._no_zip_var.get()
        project["builder"] = builder
        self._pm.write_project(project)

    # ------------------------------------------------------------------
    # accessors（供 app.py / 预览）
    # ------------------------------------------------------------------

    def get_entry(self) -> str:
        return self._entry_var.get().strip()

    def set_entry(self, entry: str) -> None:
        self._entry_var.set(entry)

    def clear_entry_error(self) -> None:
        """将入口输入框恢复为主题默认边框（清除错误红框）。"""
        try:
            self._entry_entry.configure(border_width=0)
        except Exception:
            pass

    def set_source_dir(self, d: str) -> None:
        self._source_dir = d
        self._refresh_item_list()
        self._refresh_preview()

    # ------------------------------------------------------------------
    # 预览
    # ------------------------------------------------------------------

    def refresh_preview(self, output_dir: str = "") -> None:
        self._refresh_preview(output_dir)

    def _refresh_preview(self, out_dir: str = "") -> None:
        plugin_name = Path(self._plugin_dir).name if self._plugin_dir else "插件名"
        lines: list[str] = []
        lines.append("=" * 30)
        lines.append(f"输出目录: {out_dir or f'（默认 {plugin_name}/output/）'}")

        entry = self._entry_var.get() or "（未设置）"
        no_zip = self._no_zip_var.get()
        if no_zip:
            lines.append(f"  {plugin_name}/  ← 文件夹（调试）")
        else:
            lines.append(f"  {plugin_name}.zip  ← 分发包")
        lines.append(f"    ├── manifest.json")
        lines.append(f"    ├── {entry}  ← 入口")

        b = self._builder()
        workdir = Path(self._source_dir or self._plugin_dir or ".")
        if b is not None:
            for item in b.items():
                kind = ("path" if "path" in item
                        else ("dir" if "dir" in item else "pattern"))
                rel = item.get(kind, "")
                is_entry = "entry" in item.get("tags", [])
                if kind == "pattern" and workdir.is_dir():
                    matched = evaluate_pattern(workdir, rel)
                    names = [Path(m).name for m in matched[:10]]
                    extra = (f"…共 {len(matched)} 个" if len(matched) > 10
                             else "")
                    lines.append(f"    ├── {rel}（规则）→ {', '.join(names)} {extra}")
                else:
                    mark = " ← 入口" if is_entry else ""
                    lines.append(f"    ├── {rel}{mark}")
        lines.append(f"    └── ...")

        self._preview.configure(state="normal")
        self._preview.delete("1.0", "end")
        self._preview.insert("1.0", "\n".join(lines))
        self._preview.configure(state="disabled")
