"""Training run sidecar monitor.

Tails metrics.jsonl and events.jsonl written by ArtifactWriter, applies
rules from sidecar_rules.py, and sends Windows balloon notifications for
key training events.

Usage:
    python utils/sidecar.py \\
        --log-dir results/sim_kundur/logs/standalone \\
        --contract scenarios/evaluation_contracts/sim_kundur.json

    # without a contract (scenario-id derived from directory name):
    python utils/sidecar.py --log-dir results/sim_kundur/logs/standalone

Press Ctrl+C to stop.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

# Allow running as `python utils/sidecar.py` from project root.
# Guarded so importing sidecar as a library does not mutate sys.path.
if __name__ == "__main__":  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.notifier import notify
from utils.sidecar_rules import SidecarContext, EVENT_RULES, rule_reward_decline

_DEFAULT_POLL_INTERVAL = 2.0  # seconds


# ── file tailing ──────────────────────────────────────────────────────────────

def _read_new_lines(path: Path, offset: int) -> tuple[list[dict], int]:
    """Read JSONL records appended since `offset` bytes.

    Returns (new_records, updated_offset).  Records with JSON parse errors
    are silently skipped to stay robust against mid-write truncation.

    Only advances offset to the last complete line (ending with '\\n') so that
    a partially-written line is re-read on the next poll after the writer
    finishes it.
    """
    if not path.exists():
        return [], offset
    try:
        with path.open("rb") as fh:
            fh.seek(offset)
            raw = fh.read()
    except OSError:
        return [], offset

    # Advance only to the last newline — anything after is a partial write
    last_nl = raw.rfind(b"\n")
    if last_nl == -1:
        return [], offset  # no complete line available yet
    new_offset = offset + last_nl + 1
    raw = raw[: last_nl + 1]

    records: list[dict] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return records, new_offset


# ── sidecar loop ──────────────────────────────────────────────────────────────

def run_sidecar(
    log_dir: Path,
    scenario_id: str,
    poll_interval: float = _DEFAULT_POLL_INTERVAL,
) -> None:
    """Block and watch log_dir until KeyboardInterrupt."""
    metrics_path = log_dir / "metrics.jsonl"
    events_path = log_dir / "events.jsonl"
    metrics_offset = 0
    events_offset = 0
    ctx = SidecarContext(scenario_id=scenario_id)

    print(f"[sidecar] Watching  : {log_dir}", flush=True)
    print(f"[sidecar] Scenario  : {scenario_id}", flush=True)
    print(f"[sidecar] Poll every: {poll_interval}s  (Ctrl+C to stop)", flush=True)

    while True:
        # ── Process new events first (training_start fires before first metric) ──
        new_events, events_offset = _read_new_lines(events_path, events_offset)
        for ev in new_events:
            ev_type = ev.get("type", "")
            rule_fn = EVENT_RULES.get(ev_type)
            if rule_fn is None:
                continue
            notif = rule_fn(ev, ctx)
            if notif:
                print(f"[sidecar] {notif.title} | {notif.body}", flush=True)
                notify(notif.title, notif.body)

        # ── Process new metrics (metric-based decline rule) ──────────────────
        new_metrics, metrics_offset = _read_new_lines(metrics_path, metrics_offset)
        for row in new_metrics:
            ep = row.get("episode", -1)
            reward = row.get("reward")
            if reward is not None:
                notif = rule_reward_decline(ep, float(reward), ctx)
                if notif:
                    print(f"[sidecar] {notif.title} | {notif.body}", flush=True)
                    notify(notif.title, notif.body)

        time.sleep(poll_interval)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _scenario_id_from_contract(contract_path: Path) -> str | None:
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        return contract.get("scenario_id")
    except OSError:
        return None


def _scenario_id_fallback(log_dir: Path) -> str:
    # Expected layout: results/<scenario_id>/logs/<mode>  →  parent.parent.name
    sid = log_dir.parent.parent.name
    if not sid or sid in {".", "..", ""}:
        sid = log_dir.name
        warnings.warn(
            f"[sidecar] Could not infer scenario_id from path; using '{sid}'. "
            "Pass --scenario-id or --contract to be explicit.",
            stacklevel=2,
        )
    return sid


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Sidecar monitor: tails training artifacts and sends Windows notifications."
    )
    p.add_argument("--log-dir", required=True, help="Path to logs/<mode>/ directory")
    p.add_argument("--contract", default=None,
                   help="Path to scenario contract JSON (optional; used for scenario_id)")
    p.add_argument("--scenario-id", default=None,
                   help="Override scenario ID (default: from contract or directory name)")
    p.add_argument("--poll-interval", type=float, default=_DEFAULT_POLL_INTERVAL,
                   help=f"Poll interval in seconds (default: {_DEFAULT_POLL_INTERVAL})")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    log_dir = Path(args.log_dir)

    scenario_id: str | None = args.scenario_id
    if scenario_id is None and args.contract:
        scenario_id = _scenario_id_from_contract(Path(args.contract))
    if scenario_id is None:
        scenario_id = _scenario_id_fallback(log_dir)

    try:
        run_sidecar(log_dir, scenario_id, args.poll_interval)
    except KeyboardInterrupt:
        print("\n[sidecar] Stopped.", flush=True)


if __name__ == "__main__":
    main()
