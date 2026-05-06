"""handoffs/INDEX.md 维护. 最新在最上."""

from __future__ import annotations

import datetime
from pathlib import Path

HEADER = """# Handoffs Index

> 最新 handoff 在最上. 新会话进来读最上一行的 path.
> 维护: scripts/research_loop/handoff_index.py
"""


def _utc_now_z() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def init_index_if_missing(path: Path | str) -> None:
    p = Path(path)
    if p.exists():
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(HEADER + chr(10), encoding="utf-8")


def add_handoff_entry(
    index_path: Path | str,
    round_idx: int,
    *,
    path_relative: str,
    ctx_tok: int,
    summary: str,
    when_utc: str | None = None,
) -> None:
    """Prepend 一条 handoff entry (header 后, 最新在上).

    path_relative: handoff 文件相对路径 (e.g. "2026-05-07_R01.md").
    Keyword-only 防 caller 把两个 path 弄混.
    """
    if not path_relative:
        raise ValueError("path_relative required")
    p = Path(index_path)
    init_index_if_missing(p)
    when = when_utc or _utc_now_z()
    nl = chr(10)
    line = (f"- **R{round_idx:02d}** | {when} | ctx={ctx_tok} | "
            f"[{path_relative}]({path_relative}) — {summary}" + nl)
    text = p.read_text(encoding="utf-8")
    marker = "维护: scripts/research_loop/handoff_index.py" + nl
    insert_at = text.find(marker)
    if insert_at < 0:
        new = text.rstrip() + nl + nl + line
    else:
        marker_end = insert_at + len(marker)
        head = text[:marker_end] + nl
        rest = text[marker_end:].lstrip(nl)
        new = head + line + rest
    p.write_text(new, encoding="utf-8")
