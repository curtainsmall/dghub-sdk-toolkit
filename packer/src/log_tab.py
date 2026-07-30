"""Log tab — collects output from all other tabs, with severity coloring."""

import datetime
from typing import Any, Optional

import customtkinter as ctk

# 日志级别 → 前景色。颜色取在浅色/深色文本框背景下均可读的中间色调
# （tkinter tag 只接受单色，无法用 CTk 的 (light, dark) 二元组）。
_LEVEL_COLORS: dict[str, str] = {
    "error":   "#E5484D",   # 错误 / 校验失败
    "warning": "#D9822B",   # 警告
    "success": "#30A46C",   # 完成 / 校验通过
    "hint":    "#3E82E6",   # 提示
    "info":    "#149ECA",   # 开始 / 运行
    "section": "#9F7AEA",   # === 阶段标题 ===（紫，区别于各严重级别）
}


def _classify(msg: str) -> Optional[str]:
    """按消息前缀判定日志级别，返回对应 tag 名（None = 普通行，用默认色）。"""
    if msg.startswith("[错误]") or msg.startswith("[校验失败]"):
        return "error"
    if msg.startswith("[警告]"):
        return "warning"
    if msg.startswith("[完成]") or msg.startswith("校验通过"):
        return "success"
    if msg.startswith("[提示]"):
        return "hint"
    if msg.startswith("[开始]") or msg.startswith("[运行]"):
        return "info"
    if msg.startswith("==="):
        return "section"
    return None


class LogTab(ctk.CTkFrame):
    """Read-only log viewer that collects messages from all tabs."""

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._text = ctk.CTkTextbox(
            self, wrap="word", font=("Consolas", 11), state="disabled")
        self._text.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # 注册颜色标签
        for level, color in _LEVEL_COLORS.items():
            self._text.tag_config(level, foreground=color)

    def write(self, msg: str) -> None:
        """Append a timestamped, severity-colored message to the log."""
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        level = _classify(msg)
        line = f"[{ts}] {msg}\n"
        self._text.configure(state="normal")
        if level:
            self._text.insert("end", line, level)
        else:
            self._text.insert("end", line)
        self._text.see("end")
        self._text.configure(state="disabled")
        self.update_idletasks()

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")
