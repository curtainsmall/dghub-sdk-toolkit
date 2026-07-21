"""Manifest editor tab."""

import json
from tkinter import messagebox
from typing import Any, Optional

import customtkinter as ctk

from .manifest_validator import VALID_FIELD_TYPES, validate_manifest

FIELD_TYPE_LABELS: dict[str, str] = {
    "bool": "开关 (bool)",
    "percent": "百分比 0-100 (percent)",
    "duration": "秒数 (duration)",
    "number": "数字 (number)",
    "text": "文本 (text)",
    "select": "下拉框 (select)",
    "channel": "通道选择 a/b/both (channel)",
    "preset": "波形预设 (preset)",
    "path": "路径 (path)",
}


class ManifestTab(ctk.CTkFrame):
    """Tab for creating / editing manifest.json."""

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, **kwargs)
        # internal data
        self._sections: list[dict[str, Any]] = []
        self._section_buttons: list[ctk.CTkButton] = []
        self._selected_section: int = 0
        self._field_buttons: list[ctk.CTkButton] = []
        self._selected_field: int = 0
        self._plugin_dir: Optional[str] = None
        self._controls: list[ctk.CTkBaseClass] = []

        self._build_ui()
        self._set_enabled(False)

    def _set_enabled(self, enabled: bool) -> None:
        """Enable or disable all interactive controls."""
        state = "normal" if enabled else "disabled"
        for w in self._controls:
            try:
                w.configure(state=state)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)  # header
        self.grid_rowconfigure(1, weight=1)  # main content

        # -- header --
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="Manifest 编辑器",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")

        # -- main area: left (form) + right (preview) --
        main = ctk.CTkFrame(self)
        main.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        main.grid_columnconfigure(0, weight=2)
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(0, weight=1)

        left = ctk.CTkScrollableFrame(main)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        right = ctk.CTkFrame(main)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        # -- left side: form --
        self._build_basic_info(left)
        self._build_capabilities(left)
        self._build_schema_editor(left)

        # -- right side: preview --
        preview_header = ctk.CTkFrame(right, fg_color="transparent")
        preview_header.pack(anchor="nw", fill="x", pady=(0, 5))
        ctk.CTkLabel(preview_header, text="JSON 预览",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        self._preview_wrap_var = ctk.BooleanVar(value=False)
        self._preview_wrap_cb = ctk.CTkCheckBox(preview_header, text="换行", variable=self._preview_wrap_var,
                        command=self._toggle_preview_wrap)
        self._preview_wrap_cb.pack(side="right", padx=5)
        self._controls.append(self._preview_wrap_cb)
        self._preview = ctk.CTkTextbox(right, wrap="none", font=("Consolas", 12))
        self._preview.pack(fill="both", expand=True)

        # -- bottom bar --
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        bottom.grid_columnconfigure(0, weight=1)

        self._error_label = ctk.CTkLabel(bottom, text="", text_color="red")
        self._error_label.pack(side="left", padx=5)

        self._save_btn = ctk.CTkButton(bottom, text="保存 manifest.json",
                      command=self._save_manifest, width=150)
        self._save_btn.pack(side="right", padx=5)
        self._controls.append(self._save_btn)

    # ------------------------------------------------------------------
    # basic info
    # ------------------------------------------------------------------

    def _build_basic_info(self, parent: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(frame, text="基本信息",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))

        self._fields: dict[str, Any] = {}
        for key, label, placeholder in [
            ("id", "插件 ID", "my_plugin (小写字母开头)"),
            ("name", "插件名称", "我的插件"),
            ("version", "版本号", "0.1.0"),
            ("author", "作者 (可选)", ""),
            ("description", "描述 (可选)", "一句话简介"),
            ("homepage", "主页 (可选)", "https://..."),
            ("entry", "入口文件 (可选)", "main.py"),
        ]:
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)
            row.grid_columnconfigure(0, weight=0, minsize=100)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text=label, anchor="w").grid(row=0, column=0, sticky="w")
            widget: Any = ctk.CTkEntry(row, placeholder_text=placeholder)
            widget.grid(row=0, column=1, sticky="ew", padx=(5, 0))
            widget.bind("<KeyRelease>", lambda e: self._refresh_preview())
            self._fields[key] = widget
            self._controls.append(widget)

    # ------------------------------------------------------------------
    # capabilities
    # ------------------------------------------------------------------

    def _build_capabilities(self, parent: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(frame, text="能力声明",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))
        self._cb_startup_check = ctk.CTkCheckBox(frame, text="startup_check (启动检查)",
                                                  command=self._refresh_preview)
        self._cb_startup_check.pack(anchor="w", padx=10, pady=(0, 10))
        self._controls.append(self._cb_startup_check)

    # ------------------------------------------------------------------
    # config schema editor
    # ------------------------------------------------------------------

    def _build_schema_editor(self, parent: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="both", expand=True, pady=(0, 10))
        ctk.CTkLabel(frame, text="Config Schema 编辑器",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))

        # sections area
        sec_frame = ctk.CTkFrame(frame)
        sec_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        sec_frame.grid_columnconfigure(0, weight=1, minsize=150)
        sec_frame.grid_columnconfigure(1, weight=2)
        sec_frame.grid_rowconfigure(0, weight=1)

        # left: section list
        sec_left = ctk.CTkFrame(sec_frame)
        sec_left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        sec_left.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(sec_left, text="配置分组 (Section)",
                     font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, pady=(5, 5))
        self._section_container = ctk.CTkScrollableFrame(sec_left)
        self._section_container.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self._section_container.grid_columnconfigure(0, weight=1)

        sec_btn_frame = ctk.CTkFrame(sec_left, fg_color="transparent")
        sec_btn_frame.grid(row=2, column=0, pady=5)
        ctk.CTkButton(sec_btn_frame, text="+ 添加分组", width=90,
                      command=self._add_section).pack(side="left", padx=2)
        ctk.CTkButton(sec_btn_frame, text="删除", width=60,
                      command=self._delete_section).pack(side="left", padx=2)
        for btn in sec_btn_frame.winfo_children():
            self._controls.append(btn)

        # right: fields in selected section
        sec_right = ctk.CTkFrame(sec_frame)
        sec_right.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        sec_right.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(sec_right, text="字段列表 (Fields)",
                     font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, pady=(5, 5))
        self._field_container = ctk.CTkScrollableFrame(sec_right)
        self._field_container.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self._field_container.grid_columnconfigure(0, weight=1)

        fld_btn_frame = ctk.CTkFrame(sec_right, fg_color="transparent")
        fld_btn_frame.grid(row=2, column=0, pady=5)
        ctk.CTkButton(fld_btn_frame, text="+ 添加字段", width=90,
                      command=self._add_field).pack(side="left", padx=2)
        ctk.CTkButton(fld_btn_frame, text="删除字段", width=80,
                      command=self._delete_field).pack(side="left", padx=2)
        for btn in fld_btn_frame.winfo_children():
            self._controls.append(btn)

    # ------------------------------------------------------------------
    # section management
    # ------------------------------------------------------------------

    def _add_section(self) -> None:
        dialog = ctk.CTkInputDialog(text="输入分组名称 (section):", title="添加分组")
        name = dialog.get_input()
        if name and name.strip():
            self._sections.append({"section": name.strip(), "fields": []})
            self._selected_section = len(self._sections) - 1  # auto-select new
            self._refresh_section_list()
            self._refresh_fields_display()
            self._refresh_preview()

    def _delete_section(self) -> None:
        sel = self._get_selected_section_index()
        if sel is not None and 0 <= sel < len(self._sections):
            if messagebox.askyesno("确认", f"删除分组 '{self._sections[sel]['section']}'？"):
                self._sections.pop(sel)
                # keep selection valid
                if self._selected_section >= len(self._sections):
                    self._selected_section = max(0, len(self._sections) - 1)
                self._refresh_section_list()
                self._refresh_fields_display()
                self._refresh_preview()

    def _on_section_click(self, idx: int) -> None:
        """Handle click on a section button - update selection and highlight."""
        if 0 <= idx < len(self._sections):
            self._selected_section = idx
            self._selected_field = 0
            self._refresh_section_list()
            self._refresh_fields_display()
    
    def _on_field_click(self, idx: int) -> None:
        """Click a field button -> open edit dialog directly (no highlight)."""
        sec = self._get_current_section()
        if sec is None or idx >= len(sec["fields"]):
            return
        self._selected_field = idx
        old = sec["fields"][idx]
        updated = self._field_dialog(existing=old)
        if updated:
            sec["fields"][idx] = updated
            self._refresh_fields_display()
            self._refresh_preview()
    
    def _get_selected_section_index(self) -> Optional[int]:
        if 0 <= self._selected_section < len(self._sections):
            return self._selected_section
        return None
    
    def _refresh_section_list(self) -> None:
        """Rebuild section buttons with highlight on the selected one."""
        for btn in self._section_buttons:
            btn.destroy()
        self._section_buttons.clear()
    
        for i, sec in enumerate(self._sections):
            selected = (i == self._selected_section)
            btn = ctk.CTkButton(
                self._section_container,
                text=sec["section"],
                anchor="w",
                height=28,
                fg_color="#2B6EA6" if selected else "transparent",
                text_color=("white" if selected else None),
                hover_color="#1F5380",
                command=lambda idx=i: self._on_section_click(idx),
            )
            btn.grid(row=i, column=0, sticky="ew", padx=2, pady=1)
            self._section_buttons.append(btn)
    
    def _refresh_fields_display(self) -> None:
        """Rebuild field buttons without persistent highlight (no selected state)."""
        for btn in self._field_buttons:
            btn.destroy()
        self._field_buttons.clear()
    
        sec = self._get_current_section()
        if sec is None:
            return
    
        for j, f in enumerate(sec["fields"]):
            label = f"[{j}] {f.get('key', '?')} ({f.get('type', '?')}) - {f.get('label', '?')}"
            btn = ctk.CTkButton(
                self._field_container,
                text=label,
                anchor="w",
                height=28,
                fg_color="transparent",
                hover_color="#1F5380",
                command=lambda idx=j: self._on_field_click(idx),
            )
            btn.grid(row=j, column=0, sticky="ew", padx=2, pady=1)
            self._field_buttons.append(btn)

    # ------------------------------------------------------------------
    # field management
    # ------------------------------------------------------------------

    def _get_current_section(self) -> Optional[dict]:
        idx = self._get_selected_section_index()
        if idx is not None and 0 <= idx < len(self._sections):
            return self._sections[idx]
        return None

    def _add_field(self) -> None:
        sec = self._get_current_section()
        if sec is None:
            messagebox.showinfo("提示", "请先选择一个配置分组")
            return
        field = self._field_dialog()
        if field:
            sec["fields"].append(field)
            self._refresh_fields_display()
            self._refresh_preview()

    def _delete_field(self) -> None:
        sec = self._get_current_section()
        if sec is None or not sec["fields"]:
            return
        idx = self._selected_field
        if idx >= len(sec["fields"]):
            return
        if messagebox.askyesno("确认", f"删除字段 '{sec['fields'][idx].get('key', '?')}'？"):
            sec["fields"].pop(idx)
            if self._selected_field >= len(sec["fields"]):
                self._selected_field = max(0, len(sec["fields"]) - 1)
            self._refresh_fields_display()
            self._refresh_preview()

    def _field_dialog(self, existing: Optional[dict] = None) -> Optional[dict]:
        """Open a dialog for adding/editing a field. Returns field dict or None."""
        win = ctk.CTkToplevel(self)
        win.title("编辑字段" if existing else "添加字段")
        win.geometry("420x480")
        win.transient(self)
        win.grab_set()

        entries: dict[str, Any] = {}
        row = 0

        def add_row(label: str, key: str,
                    widget_type: str = "entry",
                    options: Optional[list[str]] = None) -> None:
            nonlocal row
            ctk.CTkLabel(win, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=3)
            if widget_type == "entry":
                e = ctk.CTkEntry(win, width=250)
                e.grid(row=row, column=1, padx=10, pady=3)
                if existing and key in existing:
                    val = existing[key]
                    if isinstance(val, (int, float)):
                        val = str(val)
                    elif isinstance(val, list):
                        val = ", ".join(str(v) for v in val)
                    elif isinstance(val, bool):
                        val = "true" if val else "false"
                    e.insert(0, str(val) if val is not None else "")
                entries[key] = e
            elif widget_type == "combo":
                cb = ctk.CTkOptionMenu(win, values=options or [], width=250)
                cb.grid(row=row, column=1, padx=10, pady=3)
                if existing and key in existing:
                    cb.set(str(existing[key]))
                else:
                    cb.set(options[0] if options else "")
                entries[key] = cb
            row += 1

        add_row("Key", "key")
        add_row("类型 (Type)", "type", "combo", list(FIELD_TYPE_LABELS.keys()))
        add_row("Label", "label")
        add_row("默认值 (default)", "default")
        add_row("描述 (description)", "description")
        add_row("最小值 (min)", "min")
        add_row("最大值 (max)", "max")
        add_row("步长 (step)", "step")
        add_row("选项 (options, 逗号分隔)", "options")

        result: Optional[dict] = None

        def on_ok() -> None:
            nonlocal result
            field: dict[str, Any] = {
                "key": entries["key"].get().strip(),
                "type": entries["type"].get(),
                "label": entries["label"].get().strip(),
            }
            if entries["default"].get().strip():
                field["default"] = entries["default"].get().strip()
            if entries["description"].get().strip():
                field["description"] = entries["description"].get().strip()
            if entries["min"].get().strip():
                field["min"] = entries["min"].get().strip()
            if entries["max"].get().strip():
                field["max"] = entries["max"].get().strip()
            if entries["step"].get().strip():
                field["step"] = entries["step"].get().strip()
            if entries["options"].get().strip():
                field["options"] = [s.strip() for s in entries["options"].get().split(",") if s.strip()]
            if not field["key"]:
                messagebox.showwarning("警告", "Key 不能为空", parent=win)
                return
            if not field["label"]:
                messagebox.showwarning("警告", "Label 不能为空", parent=win)
                return
            result = field
            win.destroy()

        ctk.CTkButton(win, text="确定", command=on_ok).grid(row=row, column=0, pady=15)
        ctk.CTkButton(win, text="取消", command=win.destroy).grid(row=row, column=1, pady=15)

        self.wait_window(win)
        return result

    # ------------------------------------------------------------------
    # directory selection
    # ------------------------------------------------------------------

    def set_plugin_dir(self, d: str) -> None:
        """Set plugin directory from shared picker and try to load manifest."""
        self._set_enabled(True)
        self._plugin_dir = d
        # try to load existing manifest
        manifest_path = os.path.join(d, "manifest.json")
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._load_manifest(data)
            except (json.JSONDecodeError, Exception) as exc:
                messagebox.showwarning("加载失败", f"无法解析 manifest.json: {exc}")

    # ------------------------------------------------------------------
    # load / save
    # ------------------------------------------------------------------

    def _get_field_value(self, key: str) -> str:
        """Get value from a basic-info field widget (CTkEntry or CTkTextbox)."""
        w = self._fields[key]
        if isinstance(w, ctk.CTkTextbox):
            return w.get("1.0", "end").strip()
        return w.get().strip()

    def _set_field_value(self, key: str, val: str) -> None:
        """Set value of a basic-info field widget (CTkEntry or CTkTextbox)."""
        w = self._fields[key]
        if isinstance(w, ctk.CTkTextbox):
            w.delete("1.0", "end")
            w.insert("1.0", val)
        else:
            w.delete(0, "end")
            w.insert(0, val)

    def _load_manifest(self, data: dict) -> None:
        """Populate the form from an existing manifest dict."""
        for key in self._fields:
            if key in data:
                val = data[key]
                if isinstance(val, bool):
                    val = str(val).lower()
                self._set_field_value(key, str(val) if val is not None else "")
            else:
                self._set_field_value(key, "")

        caps = data.get("capabilities", {})
        self._cb_startup_check.deselect()
        if caps.get("startup_check"):
            self._cb_startup_check.select()

        # sections
        self._sections = list(data.get("config_schema", []))
        self._selected_field = 0
        self._refresh_section_list()
        self._refresh_fields_display()
        self._refresh_preview()

    def _build_manifest(self) -> dict:
        """Build manifest dict from form state."""
        data: dict[str, Any] = {}
        for key in self._fields:
            val = self._get_field_value(key)
            if val:
                data[key] = val

        if self._cb_startup_check.get():
            data["capabilities"] = {"startup_check": True}

        if self._sections:
            data["config_schema"] = self._sections

        return data

    def _save_manifest(self) -> None:
        if not self._plugin_dir:
            messagebox.showwarning("警告", "请先选择插件目录")
            return

        data = self._build_manifest()
        if not data.get("id") or not data.get("name") or not data.get("version"):
            messagebox.showwarning("警告", "请至少填写 id, name, version")
            return

        errors = validate_manifest(data)
        if errors:
            self._error_label.configure(text="; ".join(errors[:3]))
            messagebox.showwarning("校验失败", "\n".join(errors))
            return

        self._error_label.configure(text="")

        path = os.path.join(self._plugin_dir, "manifest.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("成功", f"manifest.json 已保存到:\n{path}")
        except Exception as exc:
            messagebox.showerror("错误", f"保存失败: {exc}")

        self._refresh_preview()

    # ------------------------------------------------------------------
    # preview
    # ------------------------------------------------------------------

    def _refresh_preview(self) -> None:
        data = self._build_manifest()
        text = json.dumps(data, ensure_ascii=False, indent=2)
        self._preview.configure(state="normal")
        self._preview.delete("1.0", "end")
        self._preview.insert("1.0", text)
        self._preview.configure(state="disabled")

    def _toggle_preview_wrap(self) -> None:
        """Toggle JSON preview word wrap."""
        wrap_mode = "word" if self._preview_wrap_var.get() else "none"
        self._preview.configure(wrap=wrap_mode)

    # ------------------------------------------------------------------
    # external access
    # ------------------------------------------------------------------

    def get_plugin_dir(self) -> Optional[str]:
        return self._plugin_dir

    def get_manifest_data(self) -> dict:
        return self._build_manifest()


import os  # noqa: E402 (needed for _load_manifest / _save_manifest)
