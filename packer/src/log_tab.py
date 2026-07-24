"""Log tab — collects output from all other tabs."""

import datetime
from typing import Any

import customtkinter as ctk


class LogTab(ctk.CTkFrame):
    """Read-only log viewer that collects messages from all tabs."""

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._text = ctk.CTkTextbox(
            self, wrap="word", font=("Consolas", 11), state="disabled")
        self._text.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

    def write(self, msg: str) -> None:
        """Append a timestamped message to the log."""
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._text.configure(state="normal")
        self._text.insert("end", f"[{ts}] {msg}\n")
        self._text.see("end")
        self._text.configure(state="disabled")
        self.update_idletasks()

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")
