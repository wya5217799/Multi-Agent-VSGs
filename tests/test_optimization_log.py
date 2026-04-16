# tests/test_optimization_log.py
"""Tests for engine.optimization_log — append-only optimization memory layer."""
import json
from pathlib import Path

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _contracts_dir(tmp_path: Path) -> Path:
    d = tmp_path / "contracts"
    d.mkdir()
    return d


def _write_log(contracts_dir: Path, scenario: str, lines: list[dict]) -> Path:
    p = contracts_dir / f"optimization_log_{scenario}.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in lines), encoding="utf-8")
    return p


# ── load_log ──────────────────────────────────────────────────────────────────

def test_load_log_missing_file_returns_empty(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", _contracts_dir(tmp_path))
    from engine.optimization_log import load_log
    assert load_log("kundur") == []


def test_load_log_returns_records_in_order(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    cd = _contracts_dir(tmp_path)
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", cd)
    records = [
        {"type": "optimization", "opt_id": "opt_kd_20260416_01", "ts": "2026-04-16T10:00:00+08:00",
         "scenario": "kundur", "scope": "transferable", "status": "applied",
         "problem": "r_h too high", "hypothesis": "lower PHI_H", "changes": []},
        {"type": "outcome", "opt_id": "opt_kd_20260416_01", "ts": "2026-04-16T20:00:00+08:00",
         "verdict": "effective", "summary": "settled_rate 0.05→0.18"},
    ]
    _write_log(cd, "kundur", records)
    from engine.optimization_log import load_log
    result = load_log("kundur")
    assert len(result) == 2
    assert result[0]["type"] == "optimization"
    assert result[1]["type"] == "outcome"


def test_load_log_skips_empty_lines_and_malformed(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    cd = _contracts_dir(tmp_path)
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", cd)
    path = cd / "optimization_log_kundur.jsonl"
    path.write_text(
        '{"type":"optimization","opt_id":"opt_kd_20260416_01"}\n\n{broken\n',
        encoding="utf-8",
    )
    from engine.optimization_log import load_log
    result = load_log("kundur")
    assert len(result) == 1
    assert result[0]["opt_id"] == "opt_kd_20260416_01"


# ── append_optimization ───────────────────────────────────────────────────────

def test_append_optimization_returns_opt_id(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", _contracts_dir(tmp_path))
    from engine.optimization_log import append_optimization
    opt_id = append_optimization("kundur", {
        "scenario": "kundur",
        "scope": "transferable",
        "status": "applied",
        "problem": "r_h dominates",
        "hypothesis": "lower PHI_H balances reward",
        "changes": [{"param": "PHI_H", "from": 1.0, "to": 0.3}],
    })
    assert opt_id.startswith("opt_kd_")
    assert len(opt_id.split("_")) == 4  # opt_kd_YYYYMMDD_NN


def test_append_optimization_auto_fills_type_ts(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    cd = _contracts_dir(tmp_path)
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", cd)
    from engine.optimization_log import append_optimization, load_log
    append_optimization("kundur", {
        "scenario": "kundur",
        "scope": "kundur_only",
        "status": "applied",
        "problem": "p",
        "hypothesis": "h",
        "changes": [],
    })
    rows = load_log("kundur")
    assert rows[0]["type"] == "optimization"
    assert "ts" in rows[0]
    assert rows[0]["ts"]  # non-empty


def test_append_optimization_seq_increments_per_day(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    cd = _contracts_dir(tmp_path)
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", cd)
    from engine.optimization_log import append_optimization
    base = {"scenario": "kundur", "scope": "transferable", "status": "applied",
            "problem": "p", "hypothesis": "h", "changes": []}
    id1 = append_optimization("kundur", base.copy())
    id2 = append_optimization("kundur", base.copy())
    seq1 = id1.split("_")[-1]
    seq2 = id2.split("_")[-1]
    assert int(seq2) == int(seq1) + 1


def test_append_optimization_ne39_prefix(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", _contracts_dir(tmp_path))
    from engine.optimization_log import append_optimization
    opt_id = append_optimization("ne39", {
        "scenario": "ne39",
        "scope": "ne39_only",
        "status": "applied",
        "problem": "p",
        "hypothesis": "h",
        "changes": [],
    })
    assert opt_id.startswith("opt_ne_")


def test_append_optimization_missing_required_field_raises(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", _contracts_dir(tmp_path))
    from engine.optimization_log import append_optimization
    with pytest.raises(ValueError, match="Missing required"):
        append_optimization("kundur", {
            "scenario": "kundur",
            # missing scope, status, problem, hypothesis, changes
        })


def test_append_optimization_invalid_scenario_raises(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", _contracts_dir(tmp_path))
    from engine.optimization_log import append_optimization
    with pytest.raises(ValueError, match="scenario"):
        append_optimization("bad_scenario", {
            "scenario": "bad_scenario",
            "scope": "transferable",
            "status": "applied",
            "problem": "p",
            "hypothesis": "h",
            "changes": [],
        })


# ── append_outcome ────────────────────────────────────────────────────────────

def _seed_one_optimization(cd: Path, scenario: str, opt_id: str) -> None:
    """Write a minimal optimization record so append_outcome can validate opt_id."""
    rec = {
        "type": "optimization",
        "opt_id": opt_id,
        "ts": "2026-04-16T10:00:00+08:00",
        "scenario": scenario,
        "scope": "transferable",
        "status": "applied",
        "problem": "p",
        "hypothesis": "h",
        "changes": [],
    }
    p = cd / f"optimization_log_{scenario}.jsonl"
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def test_append_outcome_writes_record(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    cd = _contracts_dir(tmp_path)
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", cd)
    _seed_one_optimization(cd, "kundur", "opt_kd_20260416_01")
    from engine.optimization_log import append_outcome, load_log
    append_outcome(
        "kundur",
        "opt_kd_20260416_01",
        "effective",
        "settled_rate 0.05→0.18",
        confidence="high",
    )
    rows = load_log("kundur")
    outcome_rows = [r for r in rows if r.get("type") == "outcome"]
    assert len(outcome_rows) == 1
    o = outcome_rows[0]
    assert o["opt_id"] == "opt_kd_20260416_01"
    assert o["verdict"] == "effective"
    assert o["summary"] == "settled_rate 0.05→0.18"
    assert o["confidence"] == "high"
    assert o["type"] == "outcome"
    assert "ts" in o


def test_append_outcome_unknown_opt_id_raises(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", _contracts_dir(tmp_path))
    from engine.optimization_log import append_outcome
    with pytest.raises(ValueError, match="opt_id"):
        append_outcome("kundur", "opt_kd_99999999_01", "effective", "good")


def test_append_outcome_invalid_verdict_raises(tmp_path, monkeypatch):
    import engine.optimization_log as ol
    cd = _contracts_dir(tmp_path)
    monkeypatch.setattr(ol, "_CONTRACTS_DIR", cd)
    _seed_one_optimization(cd, "kundur", "opt_kd_20260416_01")
    from engine.optimization_log import append_outcome
    with pytest.raises(ValueError, match="verdict"):
        append_outcome("kundur", "opt_kd_20260416_01", "dunno", "summary")


# ── _build_opt_summary ────────────────────────────────────────────────────────

def test_build_opt_summary_empty():
    from engine.optimization_log import _build_opt_summary
    result = _build_opt_summary([])
    assert result == {"total": 0, "with_outcome": 0, "by_verdict": {}, "records": []}


def test_build_opt_summary_merges_outcome():
    from engine.optimization_log import _build_opt_summary
    records = [
        {"type": "optimization", "opt_id": "opt_kd_20260416_01",
         "scenario": "kundur", "scope": "transferable", "status": "applied",
         "problem": "p", "hypothesis": "h", "changes": []},
        {"type": "outcome", "opt_id": "opt_kd_20260416_01",
         "verdict": "effective", "summary": "good"},
    ]
    result = _build_opt_summary(records)
    assert result["total"] == 1
    assert result["with_outcome"] == 1
    assert result["by_verdict"] == {"effective": 1}
    merged = result["records"][0]
    assert merged["opt_id"] == "opt_kd_20260416_01"
    assert merged["outcome"]["verdict"] == "effective"


def test_build_opt_summary_no_outcome():
    from engine.optimization_log import _build_opt_summary
    records = [
        {"type": "optimization", "opt_id": "opt_kd_20260416_01",
         "scenario": "kundur", "scope": "transferable", "status": "applied",
         "problem": "p", "hypothesis": "h", "changes": []},
    ]
    result = _build_opt_summary(records)
    assert result["total"] == 1
    assert result["with_outcome"] == 0
    assert "outcome" not in result["records"][0]


def test_build_opt_summary_multiple_outcomes_last_wins():
    """Later outcome record overwrites earlier one for same opt_id."""
    from engine.optimization_log import _build_opt_summary
    records = [
        {"type": "optimization", "opt_id": "opt_kd_20260416_01",
         "scenario": "kundur", "scope": "transferable", "status": "applied",
         "problem": "p", "hypothesis": "h", "changes": []},
        {"type": "outcome", "opt_id": "opt_kd_20260416_01", "verdict": "inconclusive", "summary": "too early"},
        {"type": "outcome", "opt_id": "opt_kd_20260416_01", "verdict": "effective", "summary": "confirmed"},
    ]
    result = _build_opt_summary(records)
    assert result["records"][0]["outcome"]["verdict"] == "effective"
