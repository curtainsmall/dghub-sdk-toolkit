"""`.dghub-sdk/` project configuration management."""

import json
from pathlib import Path
from typing import Any, Optional


_MANIFEST_DEFAULTS: dict[str, Any] = {
    "id": "",
    "name": "",
    "version": "",
    "author": "",
    "description": "",
    "sdk": "1",
}


class ProjectManager:
    """Manages a `.dghub-sdk/` directory inside the plugin source directory.

    Each tab auto-reads/writes its own file on every change.
    No explicit "save" needed — this is transparent persistence.
    """

    def __init__(self, plugin_dir: str) -> None:
        self._root = Path(plugin_dir) / ".dghub-sdk"

    # ------------------------------------------------------------------
    # Manifest (info tab)
    # ------------------------------------------------------------------

    def read_manifest(self) -> dict[str, Any]:
        """Read `.dghub-sdk/manifest.json`, return dict (merged with defaults)."""
        data = dict(_MANIFEST_DEFAULTS)
        path = self._root / "manifest.json"
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                data.update(loaded)
            except (json.JSONDecodeError, OSError):
                pass
        return data

    def write_manifest(self, data: dict[str, Any]) -> None:
        """Write manifest data to `.dghub-sdk/manifest.json`."""
        self._root.mkdir(parents=True, exist_ok=True)
        merged = dict(_MANIFEST_DEFAULTS)
        merged.update(data)
        (self._root / "manifest.json").write_text(
            json.dumps(merged, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Dependencies (dep tab)
    # ------------------------------------------------------------------

    def read_deps(self) -> list[str]:
        """Read `.dghub-sdk/deps.json`, return list of package names."""
        path = self._root / "deps.json"
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def write_deps(self, pkgs: list[str]) -> None:
        """Write dependencies list to `.dghub-sdk/deps.json`."""
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / "deps.json").write_text(
            json.dumps(pkgs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Project config (distribute tab settings)
    # ------------------------------------------------------------------

    def read_project(self) -> dict[str, Any]:
        """Read `.dghub-sdk/project.json`, return settings dict."""
        path = self._root / "project.json"
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def write_project(self, data: dict[str, Any]) -> None:
        """Write project settings to `.dghub-sdk/project.json`."""
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / "project.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def get_plugin_id(self) -> str:
        return self.read_manifest().get("id", "")

    def get_deps_count(self) -> int:
        """Return number of declared deps (including auto dghub-sdk)."""
        deps = self.read_deps()
        return len(deps)


def project_exists(plugin_dir: str) -> bool:
    """Check if `.dghub-sdk/` exists in the given directory."""
    return (Path(plugin_dir) / ".dghub-sdk" / "manifest.json").is_file()
