"""DGHub Plugin Packer — entry point.

Usage:
    python -m packer.main
    # or after PyInstaller build: DGHubPluginPacker.exe
"""

from pathlib import Path
import sys

# Ensure src/ is in path (auto for direct runs, needed for PyInstaller)
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> None:
    # Set CustomTkinter appearance before importing the app
    import customtkinter as ctk
    ctk.set_appearance_mode("system")   # follow OS theme
    ctk.set_default_color_theme("blue")

    # Workaround: PyInstaller one-file mode may need this for
    # filedialog on Windows
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)

    from app import App
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
