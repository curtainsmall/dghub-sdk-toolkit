"""Log tab — collects leveled output from all other tabs.

着色仅限 error / warning / success 三级（红 / 橙 / 绿），其余级别默认色。
级别由调用点通过 :class:`logbus.Logger` 显式声明，本视图不解析文本前缀。
外部工具输出（sep / external 级别）按原样渲染、不加时间戳。
"""

import datetime
from typing import Any

import customtkinter as ctk

# 仅这三种级别着色；颜色取在浅色/深色文本框背景下均可读的中间色调
# （tkinter tag 只接受单色，无法用 CTk 的 (light, dark) 二元组）。
_LEVEL_COLORS: dict[str, str] = {
    "error":   "#E5484D",   # 红：中断构建 / 校验失败
    "warning": "#D9822B",   # 橙：不中断但需注意
    "success": "#30A46C",   # 绿：最终产物完成
}
# 外部工具相关级别：默认色、无时间戳（分隔头 + 原始输出）
_RAW_LEVELS = ("sep", "external")


class LogTab(ctk.CTkFrame):
    """Read-only log viewer that collects leveled messages from all tabs."""

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # 顶部操作条：手动清空（构建不再自动清空日志，历史累积）
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        bar.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(bar, text="清空", width=60,
                      command=self.clear).grid(row=0, column=1, sticky="e")

        self._text = ctk.CTkTextbox(
            self, wrap="word", font=("Consolas", 11), state="disabled")
        self._text.grid(row=1, column=0, sticky="nsew", padx=10, pady=(6, 10))

        for level, color in _LEVEL_COLORS.items():
            self._text.tag_config(level, foreground=color)

    def emit(self, msg: str, level: str = "info") -> None:
        """Append a leveled message; error/warning/success 着色，其余默认色。"""
        if level in _RAW_LEVELS:
            line = f"{msg}\n"          # 外部原样 / 分隔头：不加时间戳
        else:
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            line = f"[{ts}] {msg}\n"
        self._text.configure(state="normal")
        if level in _LEVEL_COLORS:
            self._text.insert("end", line, level)
        else:
            self._text.insert("end", line)
        self._text.see("end")
        self._text.configure(state="disabled")
        self.update_idletasks()

    def write(self, msg: str) -> None:
        """兼容入口：无级别文本按普通进度（info）记录。"""
        self.emit(msg, "info")

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")
