"""build_systems 逻辑层测试：校验、产物收集、glob 求值、entry 读取。

不涉及 GUI 与真实子进程（uv / PyInstaller），仅覆盖纯逻辑路径。
"""

from pathlib import Path

import pytest

from build_systems import (
    BUILD_SYSTEMS,
    BuildError,
    GenericSupport,
    UvSystem,
    evaluate_pattern,
    read_tool_dghub_entry,
)
from conftest import StubDistView


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------


def test_registry_contains_uv_and_generic():
    assert set(BUILD_SYSTEMS) == {"uv", "generic"}
    assert BUILD_SYSTEMS["uv"].id == "uv"
    assert BUILD_SYSTEMS["generic"].id == "generic"


def test_registry_ids_match_keys():
    for key, system in BUILD_SYSTEMS.items():
        assert system.id == key


# ---------------------------------------------------------------------------
# UvSystem.validate（Python 系校验）
# ---------------------------------------------------------------------------


def test_uv_validate_empty_entry(make_ctx):
    ctx, _ = make_ctx(StubDistView(entry=""))
    errors = UvSystem().validate(ctx)
    assert errors == ["入口文件不能为空"]


def test_uv_validate_rejects_non_py_entry(make_ctx):
    ctx, _ = make_ctx(StubDistView(entry="main.exe"))
    errors = UvSystem().validate(ctx)
    assert len(errors) == 1
    assert "必须是 .py 文件" in errors[0]


def test_uv_validate_missing_entry_file(make_ctx):
    ctx, _ = make_ctx(StubDistView(entry="src/main.py"))
    errors = UvSystem().validate(ctx)
    assert errors == ["入口文件不存在: src/main.py"]


def test_uv_validate_ok(make_ctx):
    ctx, _ = make_ctx(StubDistView(entry="src/main.py"))
    (ctx.source_dir / "src").mkdir()
    (ctx.source_dir / "src" / "main.py").write_text("", encoding="utf-8")
    assert UvSystem().validate(ctx) == []


def test_uv_validate_entry_case_insensitive_suffix(make_ctx):
    ctx, _ = make_ctx(StubDistView(entry="MAIN.PY"))
    (ctx.source_dir / "MAIN.PY").write_text("", encoding="utf-8")
    assert UvSystem().validate(ctx) == []


# ---------------------------------------------------------------------------
# UvSystem：manifest_entry 与 vendor 命令
# ---------------------------------------------------------------------------


def test_uv_manifest_entry_source_mode(make_ctx):
    ctx, _ = make_ctx(StubDistView(entry="src/main.py", build_exe=False))
    assert UvSystem().manifest_entry(ctx) == "src/main.py"


def test_uv_manifest_entry_exe_mode(make_ctx):
    ctx, _ = make_ctx(StubDistView(entry="src/main.py", build_exe=True))
    assert UvSystem().manifest_entry(ctx) == "testplugin.exe"


def test_uv_vendor_cmd_shape(tmp_path: Path):
    manifest = tmp_path / "pyproject.toml"
    vendor = tmp_path / "vendor"
    cmd = UvSystem()._vendor_cmd(manifest, vendor)
    assert cmd[:3] == ["uv", "pip", "install"]
    assert str(vendor) in cmd
    assert str(manifest) in cmd


# ---------------------------------------------------------------------------
# UvSystem.build_steps：无清单跳过 vendor（不触发子进程）
# ---------------------------------------------------------------------------


def test_uv_build_steps_skips_vendor_without_manifest(make_ctx):
    ctx, logs = make_ctx(StubDistView(entry="main.py", manifest=""))
    assert UvSystem().build_steps(ctx) is True
    assert any("跳过依赖打包" in line for line in logs)


def test_uv_build_steps_fails_on_missing_manifest_file(make_ctx):
    ctx, logs = make_ctx(StubDistView(
        entry="main.py", manifest="C:/nonexistent/pyproject.toml"))
    assert UvSystem().build_steps(ctx) is False
    assert any("依赖清单不存在" in line for line in logs)


def test_uv_build_steps_uses_pypi_index_env(make_ctx, monkeypatch):
    """配置镜像源时，vendor 子进程应带 UV_DEFAULT_INDEX 环境变量。"""
    import build_systems

    captured: dict = {}

    def fake_run_logged(cmd, logger, source, cwd=None, shell=False,
                        timeout=900, env=None, canceller=None):
        captured["env"] = env
        return True

    monkeypatch.setattr(build_systems, "_run_logged", fake_run_logged)
    ctx, logs = make_ctx(StubDistView(entry="main.py", manifest="x"))
    manifest = ctx.source_dir / "pyproject.toml"
    manifest.write_text("[project]\nname='x'\n", encoding="utf-8")
    ctx.dist_view.manifest = str(manifest)

    mirror = "https://pypi.tuna.tsinghua.edu.cn/simple"
    ctx.pypi_index = mirror
    assert UvSystem().build_steps(ctx) is True
    assert captured["env"]["UV_DEFAULT_INDEX"] == mirror
    assert any("镜像源" in line for line in logs)


def test_uv_build_steps_no_index_env_by_default(make_ctx, monkeypatch):
    """未配置镜像源时，env 保持 None（继承父进程环境）。"""
    import build_systems

    captured: dict = {}

    def fake_run_logged(cmd, logger, source, cwd=None, shell=False,
                        timeout=900, env=None, canceller=None):
        captured["env"] = env
        return True

    monkeypatch.setattr(build_systems, "_run_logged", fake_run_logged)
    ctx, _ = make_ctx(StubDistView(entry="main.py", manifest="x"))
    manifest = ctx.source_dir / "pyproject.toml"
    manifest.write_text("[project]\nname='x'\n", encoding="utf-8")
    ctx.dist_view.manifest = str(manifest)

    assert UvSystem().build_steps(ctx) is True
    assert captured["env"] is None


# ---------------------------------------------------------------------------
# UvSystem.collect_output
# ---------------------------------------------------------------------------


def test_uv_collect_source_mode_entry_and_vendor(make_ctx):
    ctx, _ = make_ctx(StubDistView(entry="main.py"))
    (ctx.source_dir / "main.py").write_text("", encoding="utf-8")
    vendor = ctx.output_dir / "vendor" / "pkg"
    vendor.mkdir(parents=True)
    (vendor / "mod.py").write_text("", encoding="utf-8")

    files = UvSystem().collect_output(ctx)
    arcs = [arc for _, arc in files]
    assert "main.py" in arcs
    assert "vendor/pkg/mod.py" in arcs


def test_uv_collect_missing_entry_raises(make_ctx):
    ctx, _ = make_ctx(StubDistView(entry="main.py"))
    with pytest.raises(BuildError, match="入口文件不存在"):
        UvSystem().collect_output(ctx)


def test_uv_collect_exe_mode_missing_exe_raises(make_ctx):
    ctx, _ = make_ctx(StubDistView(entry="main.py", build_exe=True))
    with pytest.raises(BuildError, match="exe 产物不存在"):
        UvSystem().collect_output(ctx)


def test_uv_collect_exe_mode_ok(make_ctx):
    ctx, _ = make_ctx(StubDistView(entry="main.py", build_exe=True))
    (ctx.output_dir / "testplugin.exe").write_bytes(b"MZ")
    files = UvSystem().collect_output(ctx)
    assert files == [(ctx.output_dir / "testplugin.exe", "testplugin.exe")]


# ---------------------------------------------------------------------------
# GenericSupport：校验与 pre-build
# ---------------------------------------------------------------------------


def test_generic_validate_only_requires_entry(make_ctx):
    # entry 可为任意扩展名，且存在性延迟到 collect_output
    ctx, _ = make_ctx(StubDistView(entry="bin/app.exe"))
    assert GenericSupport().validate(ctx) == []


def test_generic_validate_empty_entry(make_ctx):
    ctx, _ = make_ctx(StubDistView(entry=""))
    assert GenericSupport().validate(ctx) == ["入口文件不能为空"]


def test_generic_build_steps_no_prebuild(make_ctx):
    ctx, logs = make_ctx(StubDistView(entry="app.exe", pre_build=""))
    assert GenericSupport().build_steps(ctx) is True
    assert any("无 pre-build" in line for line in logs)


def test_generic_build_steps_prebuild_failure(make_ctx):
    ctx, logs = make_ctx(StubDistView(entry="app.exe", pre_build="exit 1"))
    assert GenericSupport().build_steps(ctx) is False
    assert any("pre-build 命令失败" in line for line in logs)


def test_generic_prebuild_runs_in_plugin_dir_by_default(make_ctx):
    # 未设置执行目录时，pre-build 在插件目录执行
    ctx, logs = make_ctx(StubDistView(
        entry="app.exe", pre_build="echo built > artifact.txt"))
    assert GenericSupport().build_steps(ctx) is True
    assert (ctx.plugin_dir / "artifact.txt").is_file()
    assert not (ctx.source_dir / "artifact.txt").exists()
    assert any("执行目录" in line for line in logs)


def test_generic_prebuild_runs_in_exec_dir_when_set(make_ctx, tmp_path):
    # 显式设置执行目录后，pre-build 在该目录执行
    exec_dir = tmp_path / "proj_root"
    exec_dir.mkdir()
    ctx, _ = make_ctx(StubDistView(
        entry="app.exe", pre_build="echo built > artifact.txt",
        exec_dir=str(exec_dir)))
    assert GenericSupport().build_steps(ctx) is True
    assert (exec_dir / "artifact.txt").is_file()
    assert not (ctx.plugin_dir / "artifact.txt").exists()


# ---------------------------------------------------------------------------
# GenericSupport.collect_output：entry / 精确条目 / 规则 / 冲突
# ---------------------------------------------------------------------------


def _touch(base: Path, rel: str) -> None:
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("", encoding="utf-8")


def test_generic_collect_entry_keeps_subdir(make_ctx):
    ctx, _ = make_ctx(StubDistView(entry="bin/app.exe"))
    _touch(ctx.source_dir, "bin/app.exe")
    files = GenericSupport().collect_output(ctx)
    assert files == [(ctx.source_dir / "bin/app.exe", "bin/app.exe")]


def test_generic_collect_exact_extra_files(make_ctx):
    ctx, _ = make_ctx(StubDistView(
        entry="app.exe",
        extra_files=[
            {"path": "config.json", "dest": "root"},
            {"path": "lib/helper.dll", "dest": "vendor"},
        ]))
    for rel in ("app.exe", "config.json", "lib/helper.dll"):
        _touch(ctx.source_dir, rel)

    arcs = [arc for _, arc in GenericSupport().collect_output(ctx)]
    assert "config.json" in arcs          # root → 平铺根目录
    assert "vendor/helper.dll" in arcs    # vendor → vendor/ 下平铺


def test_generic_collect_missing_exact_file_raises(make_ctx):
    ctx, _ = make_ctx(StubDistView(
        entry="app.exe",
        extra_files=[{"path": "missing.dll", "dest": "root"}]))
    _touch(ctx.source_dir, "app.exe")
    with pytest.raises(BuildError, match="附加文件不存在"):
        GenericSupport().collect_output(ctx)


def test_generic_collect_pattern_matches(make_ctx):
    ctx, _ = make_ctx(StubDistView(
        entry="app.exe",
        extra_files=[{"pattern": "*.dll", "dest": "root"}]))
    for rel in ("app.exe", "a.dll", "b.dll", "note.txt"):
        _touch(ctx.source_dir, rel)

    arcs = [arc for _, arc in GenericSupport().collect_output(ctx)]
    assert "a.dll" in arcs and "b.dll" in arcs
    assert "note.txt" not in arcs


def test_generic_collect_pattern_no_match_logs_hint(make_ctx):
    ctx, logs = make_ctx(StubDistView(
        entry="app.exe",
        extra_files=[{"pattern": "*.so", "dest": "root"}]))
    _touch(ctx.source_dir, "app.exe")
    GenericSupport().collect_output(ctx)
    assert any("规则无匹配" in line for line in logs)


def test_generic_collect_entry_not_duplicated_by_pattern(make_ctx):
    ctx, _ = make_ctx(StubDistView(
        entry="app.exe",
        extra_files=[{"pattern": "*.exe", "dest": "root"}]))
    _touch(ctx.source_dir, "app.exe")
    files = GenericSupport().collect_output(ctx)
    assert len([arc for _, arc in files if arc.endswith("app.exe")]) == 1


def test_generic_collect_same_name_conflict_raises(make_ctx):
    # 不同子目录同名文件、同一 dest → 冲突
    ctx, _ = make_ctx(StubDistView(
        entry="app.exe",
        extra_files=[
            {"path": "a/helper.dll", "dest": "root"},
            {"path": "b/helper.dll", "dest": "root"},
        ]))
    for rel in ("app.exe", "a/helper.dll", "b/helper.dll"):
        _touch(ctx.source_dir, rel)
    with pytest.raises(BuildError, match="同名冲突"):
        GenericSupport().collect_output(ctx)


def test_generic_collect_same_name_different_dest_ok(make_ctx):
    # 同名但 dest 不同（root vs vendor）→ 不冲突
    ctx, _ = make_ctx(StubDistView(
        entry="app.exe",
        extra_files=[
            {"path": "a/helper.dll", "dest": "root"},
            {"path": "b/helper.dll", "dest": "vendor"},
        ]))
    for rel in ("app.exe", "a/helper.dll", "b/helper.dll"):
        _touch(ctx.source_dir, rel)
    arcs = [arc for _, arc in GenericSupport().collect_output(ctx)]
    assert "helper.dll" in arcs
    assert "vendor/helper.dll" in arcs


def test_generic_collect_duplicate_rule_match_deduped(make_ctx):
    # 精确条目与规则命中同一文件 → 去重不报错
    ctx, _ = make_ctx(StubDistView(
        entry="app.exe",
        extra_files=[
            {"path": "helper.dll", "dest": "root"},
            {"pattern": "*.dll", "dest": "root"},
        ]))
    for rel in ("app.exe", "helper.dll"):
        _touch(ctx.source_dir, rel)
    arcs = [arc for _, arc in GenericSupport().collect_output(ctx)]
    assert arcs.count("helper.dll") == 1


# ---------------------------------------------------------------------------
# evaluate_pattern
# ---------------------------------------------------------------------------


def test_evaluate_pattern_files_only_sorted(tmp_path: Path):
    _touch(tmp_path, "b.dll")
    _touch(tmp_path, "a.dll")
    (tmp_path / "subdir.dll").mkdir()  # 同名目录不应命中
    assert evaluate_pattern(tmp_path, "*.dll") == ["a.dll", "b.dll"]


def test_evaluate_pattern_recursive(tmp_path: Path):
    _touch(tmp_path, "dist/x.js")
    _touch(tmp_path, "dist/sub/y.js")
    assert evaluate_pattern(tmp_path, "dist/**/*.js") == [
        "dist/sub/y.js",
    ] or evaluate_pattern(tmp_path, "dist/**/*.js") == [
        "dist/sub/y.js", "dist/x.js",
    ]


def test_evaluate_pattern_invalid_returns_empty(tmp_path: Path):
    assert evaluate_pattern(tmp_path, "..") == []


# ---------------------------------------------------------------------------
# read_tool_dghub_entry
# ---------------------------------------------------------------------------


def test_read_entry_from_pyproject(tmp_path: Path):
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(
        '[project]\nname = "x"\n\n[tool.dghub]\nentry = "src/main.py"\n',
        encoding="utf-8")
    assert read_tool_dghub_entry(manifest) == "src/main.py"


def test_read_entry_missing_section(tmp_path: Path):
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text('[project]\nname = "x"\n', encoding="utf-8")
    assert read_tool_dghub_entry(manifest) == ""


def test_read_entry_rejects_non_pyproject(tmp_path: Path):
    req = tmp_path / "requirements.txt"
    req.write_text("customtkinter\n", encoding="utf-8")
    assert read_tool_dghub_entry(req) == ""


def test_read_entry_nonexistent_file(tmp_path: Path):
    assert read_tool_dghub_entry(tmp_path / "pyproject.toml") == ""


def test_read_entry_invalid_toml(tmp_path: Path):
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text("[[[ broken", encoding="utf-8")
    assert read_tool_dghub_entry(manifest) == ""


def test_read_entry_non_string_value(tmp_path: Path):
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text("[tool.dghub]\nentry = 123\n", encoding="utf-8")
    assert read_tool_dghub_entry(manifest) == ""


def test_read_entry_demo_tetris_fixture():
    """以仓库内 demo/tetris 的真实 pyproject.toml 为夹具。"""
    repo_root = Path(__file__).resolve().parent.parent.parent
    manifest = repo_root / "demo" / "tetris" / "pyproject.toml"
    if not manifest.is_file():
        pytest.skip("demo/tetris/pyproject.toml not present")
    assert read_tool_dghub_entry(manifest) == "src/main.py"
