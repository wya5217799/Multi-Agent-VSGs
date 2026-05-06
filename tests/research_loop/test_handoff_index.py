"""handoff_index 单测."""
from pathlib import Path

from scripts.research_loop.handoff_index import (
    add_handoff_entry,
    init_index_if_missing,
)


def test_init_creates_header(tmp_path: Path):
    idx = tmp_path / "INDEX.md"
    init_index_if_missing(idx)
    text = idx.read_text(encoding="utf-8")
    assert "# Handoffs Index" in text


def test_add_prepends_top(tmp_path: Path):
    idx = tmp_path / "INDEX.md"
    init_index_if_missing(idx)
    add_handoff_entry(idx, round_idx=1, path_relative="2026-05-07_R01.md",
                     ctx_tok=655000, summary="phase A smoke done")
    add_handoff_entry(idx, round_idx=2, path_relative="2026-05-08_R02.md",
                     ctx_tok=695000, summary="phase B governor pivot")
    text = idx.read_text(encoding="utf-8")
    assert text.index("R02") < text.index("R01")


def test_init_idempotent(tmp_path: Path):
    idx = tmp_path / "INDEX.md"
    init_index_if_missing(idx)
    add_handoff_entry(idx, round_idx=1, path_relative="r01.md", ctx_tok=1, summary="x")
    init_index_if_missing(idx)
    assert "r01.md" in idx.read_text(encoding="utf-8")
