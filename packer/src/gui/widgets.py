"""GUI 共享组件：跨 tab 复用的小部件与样式辅助（消除重复定义）。"""

from typing import Any, Optional

import customtkinter as ctk


class ToolTip:
    """悬停提示：为控件绑定进入/离开事件，显示轻量气泡。"""

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


def reset_entry_border(entry: ctk.CTkEntry) -> None:
    """将输入框恢复为主题默认边框（清除错误红框，而非抹成无边框）。"""
    entry.configure(
        border_width=ctk.ThemeManager.theme["CTkEntry"]["border_width"],
        border_color=ctk.ThemeManager.theme["CTkEntry"]["border_color"])
