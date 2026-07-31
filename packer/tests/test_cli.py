"""CLI 层测试：CliDistView 适配、apply_input 回放、init→apply→build 端到端。

全部无 GUI、无真实 uv/PyInstaller 子进程（仅 generic 直接打包路径）。
"""

import json
import zipfile
from pathlib import Path

from backend.project_manager import ProjectManager
from backend.input_apply import apply_input
from cli.cli_view import CliDistView
from cli.cli import dispatch


def _init_generic(plugin_dir: Path) -> ProjectManager:
    pm = ProjectManager(str(plugin_dir))
    project = pm.read_project()
    project["build_system"] = "generic"
    pm.write_project(project)
    pm.write_manifest(pm.read_manifest())
    return pm


# ---------------------------------------------------------------------------
# CliDistView
# ---------------------------------------------------------------------------

def test_clidistview_generic_getters(tmp_path):
    pm = _init_generic(tmp_path)
    pm.set_bs_config("generic", "entry", "app.exe")
    pm.set_bs_config("generic", "pre_build", "echo hi")
    pm.set_bs_config("generic", "source_dir", "dist")
    view = CliDistView(pm, "generic")
    assert view.get_entry() == "app.exe"
    assert view.get_pre_build() == "echo hi"
    # source_dir 解析为绝对路径（相对插件目录）
    assert view.get_source_dir() == (tmp_path / "dist").resolve().as_posix()


def test_clidistview_uv_source_is_manifest_parent(tmp_path):
    pm = ProjectManager(str(tmp_path))
    project = pm.read_project()
    project["build_system"] = "uv"
    pm.write_project(project)
    pm.write_manifest(pm.read_manifest())
    pm.set_bs_config("uv", "manifest", "pyproject.toml")
    view = CliDistView(pm, "uv")
    # uv 源码根 = 清单所在目录
    assert view.get_source_dir() == tmp_path.resolve().as_posix()
    assert view.get_manifest() == (tmp_path / "pyproject.toml").resolve().as_posix()


# ---------------------------------------------------------------------------
# apply_input
# ---------------------------------------------------------------------------

def test_apply_input_maps_plugin_and_build(tmp_path):
    pm = _init_generic(tmp_path)
    entries = {
        "plugin": {"id": "a.b", "name": "AB", "version": "1.2.3",
                   "entry": "main.js"},
        "build": {"system": "generic", "source_dir": "out",
                  "pre_build": "make", "target": "folder"},
    }
    apply_input(pm, entries)
    manifest = pm.read_manifest()
    assert manifest["id"] == "a.b"
    assert manifest["name"] == "AB"
    assert manifest["version"] == "1.2.3"
    cfg = pm.get_bs_config("generic")
    assert cfg["entry"] == "main.js"       # entry 入 bs 命名空间
    assert cfg["source_dir"] == "out"
    assert cfg["pre_build"] == "make"
    assert pm.read_project()["target"] == "folder"


def test_apply_input_reports_applied_fields(tmp_path):
    pm = _init_generic(tmp_path)
    applied, notices = apply_input(pm, {
        "plugin": {"id": "a.b", "name": "AB", "entry": "main.js"},
        "build": {"system": "generic", "source_dir": "out"},
    })
    # 已应用字段被逐条汇报，供 CLI 打印
    assert any(a.startswith("plugin.id") for a in applied)
    assert any(a.startswith("plugin.name") for a in applied)
    assert any(a.startswith("build.source_dir") for a in applied)
    assert any(a.startswith("entry") for a in applied)


def test_apply_input_only_reports_changed_on_reapply(tmp_path):
    pm = _init_generic(tmp_path)
    entries = {"plugin": {"id": "a-b", "name": "AB"},
               "build": {"system": "generic", "source_dir": "out"}}
    applied1, _ = apply_input(pm, entries)
    assert applied1                      # 首次相对默认有变化
    applied2, _ = apply_input(pm, entries)
    assert applied2 == []                # 再次应用同值 → 无变化，不汇报


def test_apply_input_reports_reset_to_default(tmp_path):
    pm = _init_generic(tmp_path)
    apply_input(pm, {"build": {"system": "generic", "source_dir": "out"}})
    # 把 source_dir 改回默认空串——异于原值 "out"，仍算变化并汇报
    applied, _ = apply_input(pm, {"build": {"system": "generic",
                                            "source_dir": ""}})
    assert any(a.startswith("build.source_dir") for a in applied)


def test_apply_input_uv_autofills_entry_from_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.dghub]\nentry = \"src/plugin.py\"\n", encoding="utf-8")
    pm = ProjectManager(str(tmp_path))
    pm.write_manifest(pm.read_manifest())
    apply_input(pm, {"build": {"system": "uv", "manifest": "pyproject.toml"}})
    assert pm.get_bs_config("uv")["entry"] == "src/plugin.py"


# ---------------------------------------------------------------------------
# 端到端：init → apply → build（generic，无 pre-build，直接打包 zip）
# ---------------------------------------------------------------------------

def test_cli_init_apply_build_generic_zip(tmp_path):
    plugin_dir = tmp_path / "myplugin"
    plugin_dir.mkdir()
    (plugin_dir / "main.js").write_text("console.log('hi')", encoding="utf-8")

    assert dispatch(["init", str(plugin_dir), "--build-system", "generic"]) == 0

    input_file = plugin_dir / "packer-input.json"
    input_file.write_text(json.dumps({
        "plugin": {"id": "my-plugin", "name": "My Plugin", "version": "1.0.0",
                   "entry": "main.js"},
        "build": {"system": "generic", "source_dir": "."},
    }), encoding="utf-8")
    assert dispatch(["apply", str(plugin_dir)]) == 0

    out_dir = tmp_path / "out"
    assert dispatch(["build", str(plugin_dir), "--output", str(out_dir)]) == 0

    zip_path = out_dir / "myplugin.zip"
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert "manifest.json" in names
    assert "main.js" in names


def test_cli_build_without_project_fails(tmp_path):
    # 缺 .dghub-sdk/ → 用法错误码 2
    assert dispatch(["build", str(tmp_path)]) == 2


def test_cli_apply_without_project_fails(tmp_path):
    assert dispatch(["apply", str(tmp_path)]) == 2


def test_cli_global_flags_after_subcommand(tmp_path):
    # 全局标志（--no-color / -v）后置于子命令应被接受，不触发 argparse 报错
    plugin_dir = tmp_path / "gp"
    plugin_dir.mkdir()
    (plugin_dir / "main.js").write_text("x", encoding="utf-8")
    assert dispatch(["init", str(plugin_dir), "--build-system", "generic"]) == 0
    (plugin_dir / "packer-input.json").write_text(json.dumps({
        "plugin": {"id": "gp-x", "name": "GP", "version": "1.0.0",
                   "entry": "main.js"},
        "build": {"system": "generic", "source_dir": "."},
    }), encoding="utf-8")
    assert dispatch(["apply", str(plugin_dir)]) == 0
    out_dir = tmp_path / "out"
    # 全局标志放在子命令及其参数之后
    assert dispatch(["build", str(plugin_dir), "-o", str(out_dir),
                     "--no-color", "-v"]) == 0
    assert (out_dir / "gp.zip").is_file()


def test_cli_verbose_after_subcommand_without_dir(tmp_path, monkeypatch):
    # `build -v`（省略目录）不被 argparse 拒绝；dir 回退 "."，返回用法码 2（非崩溃）
    monkeypatch.chdir(tmp_path)
    assert dispatch(["build", "-v"]) == 2
