"""Unit tests for build-artefact freshness check (Module β)."""
import os
import time
from pathlib import Path

from probes.kundur.probe_state._build_check import (
    discrete_build_dependencies,
    is_build_current,
)


def test_is_build_current_fresh(tmp_path):
    slx = tmp_path / "model.slx"
    slx.write_text("dummy")
    dep = tmp_path / "build.m"
    dep.write_text("dummy")
    # Make slx newer than dep
    os.utime(dep, (time.time() - 100, time.time() - 100))
    os.utime(slx, (time.time(), time.time()))
    assert is_build_current(slx, [dep]) is True


def test_is_build_current_stale_dep(tmp_path):
    slx = tmp_path / "model.slx"
    slx.write_text("dummy")
    dep = tmp_path / "build.m"
    dep.write_text("dummy")
    os.utime(slx, (time.time() - 100, time.time() - 100))
    os.utime(dep, (time.time(), time.time()))
    assert is_build_current(slx, [dep]) is False


def test_is_build_current_missing_slx(tmp_path):
    dep = tmp_path / "build.m"
    dep.write_text("dummy")
    assert is_build_current(tmp_path / "nonexistent.slx", [dep]) is False


def test_is_build_current_missing_dep(tmp_path):
    slx = tmp_path / "model.slx"
    slx.write_text("dummy")
    assert is_build_current(slx, [tmp_path / "nonexistent.m"]) is False


def test_is_build_current_empty_deps(tmp_path):
    """slx exists and no deps => always current."""
    slx = tmp_path / "model.slx"
    slx.write_text("dummy")
    assert is_build_current(slx, []) is True


def test_discrete_build_dependencies_lists_three_files(tmp_path):
    deps = discrete_build_dependencies(tmp_path)
    names = {p.name for p in deps}
    assert "build_kundur_cvs_v3_discrete.m" in names
    assert "build_dynamic_source_discrete.m" in names
    assert "kundur_ic_cvs_v3.json" in names
