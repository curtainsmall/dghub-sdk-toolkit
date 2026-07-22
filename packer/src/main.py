"""DGHub Plugin Packer — entry point.

Usage:
    python -m packer.main
    # or after PyInstaller build: DGHubPluginPacker.exe
"""

import os
import sys

# Ensure packer/ is importable (needed when running as script or PyInstaller exe)
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_pkg_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)


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

    from packer.src.app import App
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
