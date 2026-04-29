"""Phase 4.3 / G3 closure — fixed-scenario manifest generator + loader.

Paper Sec.IV-A: "100 randomly generated scenarios" for training, "50 randomly
generated scenarios" for test. Cumulative-reward comparison (Sec.IV-C) is only
reproducible if the test set is fixed. Project closes paper-explicit gap G3 by:

  1. Deterministically generating 100 train + 50 test scenarios from a single
     seed base, materializing them as JSON manifests checked into the repo.
  2. Providing a runtime loader that lets train_simulink.py and paper_eval.py
     consume scenarios by index.

The on-disk manifest is the canonical artifact; do NOT regenerate without
explicit `--regenerate` flag (numeric drift across NumPy versions would
silently invalidate the test-set comparison).

Hard boundaries (consistent with §0 of roadmap + Z1 scope):
- No env / agent / bridge / helper / reward / build / .slx edits.
- This module is strictly a config/data layer: it generates JSONs and provides
  read-only accessors. Wiring into env reset + train CLI is a separate task.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_SETS_DIR = REPO_ROOT / "scenarios" / "kundur" / "scenario_sets"

# Paper-explicit set sizes (Sec.IV-A).
N_TRAIN_PAPER = 100
N_TEST_PAPER = 50

# Distinct seeds for train + test so the test scenarios are not a subset of
# the train scenarios. seed_train must NOT match seed_test.
SEED_TRAIN_DEFAULT = 42
SEED_TEST_DEFAULT = 43


# ---------------------------------------------------------------------------
# Scenario schema
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    """One disturbance scenario.

    Fields:
        scenario_idx: 0-based index within the set.
        disturbance_kind: 'bus' (ESS-side via load bus 7/9 proxy)
                          or 'gen' (SG-side via G1/G2/G3 Pm-step proxy, Z1)
                          or 'mixed' (Z1 + bus together — currently unused).
        target: 7 / 9 if kind='bus'; 1 / 2 / 3 if kind='gen'.
        magnitude_sys_pu: signed disturbance magnitude (sys-pu, ±[DIST_MIN, DIST_MAX]).
        comm_failed_links: list of (i, j) tuples whose link is failed for this
                           scenario. Empty by default. (Phase 5.x extension.)
    """

    scenario_idx: int
    disturbance_kind: str
    target: int
    magnitude_sys_pu: float
    comm_failed_links: tuple[tuple[int, int], ...] = field(default_factory=tuple)


@dataclass
class ScenarioSet:
    """A complete fixed scenario set (train or test)."""
    schema_version: int
    name: str
    n_scenarios: int
    seed_base: int
    disturbance_mode: str  # 'bus' | 'gen' | 'mixed'
    dist_min_sys_pu: float
    dist_max_sys_pu: float
    bus_choices: tuple[int, ...]
    scenarios: list[Scenario]


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


def generate_scenarios(
    n: int,
    seed_base: int,
    name: str,
    disturbance_mode: str = "gen",
    dist_min_sys_pu: Optional[float] = None,
    dist_max_sys_pu: Optional[float] = None,
) -> ScenarioSet:
    """Deterministic generator.

    Default disturbance_mode='gen' (SG-side, Z1) since the project's allow-listed
    disturbance topology that gives ESS H/D leverage is the SG-side proxy.
    Manifest also supports 'bus' for ESS-side proxy (P4.1 path).
    """
    if disturbance_mode == "gen":
        bus_choices: tuple[int, ...] = (1, 2, 3)
    elif disturbance_mode == "bus":
        bus_choices = (7, 9)
    elif disturbance_mode == "mixed":
        bus_choices = (1, 2, 3, 7, 9)
    else:
        raise ValueError(
            f"disturbance_mode={disturbance_mode!r} not in {{'gen','bus','mixed'}}"
        )

    if dist_min_sys_pu is None or dist_max_sys_pu is None:
        from scenarios.kundur.config_simulink import DIST_MIN, DIST_MAX
        dist_min_sys_pu = float(DIST_MIN) if dist_min_sys_pu is None else dist_min_sys_pu
        dist_max_sys_pu = float(DIST_MAX) if dist_max_sys_pu is None else dist_max_sys_pu

    rng = np.random.default_rng(seed_base)
    scenarios: list[Scenario] = []
    for k in range(n):
        target = int(rng.choice(list(bus_choices)))
        sign = +1.0 if rng.random() < 0.5 else -1.0
        mag = float(rng.uniform(dist_min_sys_pu, dist_max_sys_pu)) * sign
        kind = "gen" if target in (1, 2, 3) else "bus"
        scenarios.append(Scenario(
            scenario_idx=k,
            disturbance_kind=kind,
            target=target,
            magnitude_sys_pu=mag,
            comm_failed_links=(),
        ))

    return ScenarioSet(
        schema_version=1,
        name=name,
        n_scenarios=n,
        seed_base=seed_base,
        disturbance_mode=disturbance_mode,
        dist_min_sys_pu=float(dist_min_sys_pu),
        dist_max_sys_pu=float(dist_max_sys_pu),
        bus_choices=tuple(bus_choices),
        scenarios=scenarios,
    )


# ---------------------------------------------------------------------------
# Serialize / deserialize
# ---------------------------------------------------------------------------


def serialize(set_obj: ScenarioSet) -> dict:
    return {
        "schema_version": set_obj.schema_version,
        "name": set_obj.name,
        "n_scenarios": set_obj.n_scenarios,
        "seed_base": set_obj.seed_base,
        "disturbance_mode": set_obj.disturbance_mode,
        "dist_min_sys_pu": set_obj.dist_min_sys_pu,
        "dist_max_sys_pu": set_obj.dist_max_sys_pu,
        "bus_choices": list(set_obj.bus_choices),
        "scenarios": [
            {
                "scenario_idx": s.scenario_idx,
                "disturbance_kind": s.disturbance_kind,
                "target": s.target,
                "magnitude_sys_pu": s.magnitude_sys_pu,
                "comm_failed_links": [list(l) for l in s.comm_failed_links],
            }
            for s in set_obj.scenarios
        ],
    }


def deserialize(d: dict) -> ScenarioSet:
    if d.get("schema_version") != 1:
        raise ValueError(f"unsupported schema_version {d.get('schema_version')}")
    scenarios = [
        Scenario(
            scenario_idx=int(s["scenario_idx"]),
            disturbance_kind=str(s["disturbance_kind"]),
            target=int(s["target"]),
            magnitude_sys_pu=float(s["magnitude_sys_pu"]),
            comm_failed_links=tuple(tuple(map(int, l)) for l in s.get("comm_failed_links", [])),
        )
        for s in d["scenarios"]
    ]
    return ScenarioSet(
        schema_version=int(d["schema_version"]),
        name=str(d["name"]),
        n_scenarios=int(d["n_scenarios"]),
        seed_base=int(d["seed_base"]),
        disturbance_mode=str(d["disturbance_mode"]),
        dist_min_sys_pu=float(d["dist_min_sys_pu"]),
        dist_max_sys_pu=float(d["dist_max_sys_pu"]),
        bus_choices=tuple(int(b) for b in d["bus_choices"]),
        scenarios=scenarios,
    )


def load_manifest(path: Path | str) -> ScenarioSet:
    with Path(path).open("r", encoding="utf-8") as f:
        return deserialize(json.load(f))


def save_manifest(set_obj: ScenarioSet, path: Path | str) -> None:
    with Path(path).open("w", encoding="utf-8") as f:
        json.dump(serialize(set_obj), f, indent=2)


# ---------------------------------------------------------------------------
# Disturbance-type translation (manifest target → KUNDUR_DISTURBANCE_TYPE)
# ---------------------------------------------------------------------------


def scenario_to_disturbance_type(scenario: Scenario) -> str:
    """Map a Scenario record to the env's `_disturbance_type` string."""
    if scenario.disturbance_kind == "gen":
        return f"pm_step_proxy_g{scenario.target}"
    if scenario.disturbance_kind == "bus":
        if scenario.target == 7:
            return "pm_step_proxy_bus7"
        if scenario.target == 9:
            return "pm_step_proxy_bus9"
        raise ValueError(f"unsupported bus target {scenario.target}")
    if scenario.disturbance_kind == "vsg":
        # 2026-04-30 Probe B-ESS: single-ESS direct Pm injection.
        # target ∈ {1, 2, 3, 4} (1-indexed ES{i}).
        if scenario.target in (1, 2, 3, 4):
            return f"pm_step_single_es{scenario.target}"
        raise ValueError(
            f"unsupported vsg target {scenario.target}; must be 1/2/3/4"
        )
    raise ValueError(f"unsupported disturbance_kind {scenario.disturbance_kind}")


# ---------------------------------------------------------------------------
# CLI: regenerate train + test manifests
# ---------------------------------------------------------------------------


def _regenerate_default_manifests() -> None:
    """Materialize the default v3-paper-replication train+test sets."""
    SCENARIO_SETS_DIR.mkdir(parents=True, exist_ok=True)
    train_path = SCENARIO_SETS_DIR / "v3_paper_train_100.json"
    test_path = SCENARIO_SETS_DIR / "v3_paper_test_50.json"

    train_set = generate_scenarios(
        n=N_TRAIN_PAPER,
        seed_base=SEED_TRAIN_DEFAULT,
        name="v3_paper_train_100",
        disturbance_mode="gen",  # Z1 finding: SG-side proxy is the only allow-listed leverage-correct topology
    )
    test_set = generate_scenarios(
        n=N_TEST_PAPER,
        seed_base=SEED_TEST_DEFAULT,
        name="v3_paper_test_50",
        disturbance_mode="gen",
    )
    save_manifest(train_set, train_path)
    save_manifest(test_set, test_path)
    print(f"  wrote {train_path}  ({train_set.n_scenarios} scenarios)")
    print(f"  wrote {test_path}  ({test_set.n_scenarios} scenarios)")

    # Sanity print a few entries
    print("  train[0..2]:", [
        f"{s.disturbance_kind}:{s.target} @ {s.magnitude_sys_pu:+.3f}"
        for s in train_set.scenarios[:3]
    ])
    print("  test[0..2]:", [
        f"{s.disturbance_kind}:{s.target} @ {s.magnitude_sys_pu:+.3f}"
        for s in test_set.scenarios[:3]
    ])

    # Distribution check
    for label, st in [("train", train_set), ("test", test_set)]:
        from collections import Counter
        kinds = Counter(s.disturbance_kind for s in st.scenarios)
        targets = Counter(s.target for s in st.scenarios)
        signs = Counter("pos" if s.magnitude_sys_pu >= 0 else "neg" for s in st.scenarios)
        print(f"  {label} kinds={dict(kinds)} targets={dict(targets)} signs={dict(signs)}")


def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument(
        "--regenerate",
        action="store_true",
        help="Regenerate the default train + test manifests (overwrites existing JSONs).",
    )
    p.add_argument(
        "--show",
        action="store_true",
        help="Show summary of existing manifests.",
    )
    args = p.parse_args()
    if args.regenerate:
        print("Regenerating default scenario manifests ...")
        _regenerate_default_manifests()
    if args.show:
        for f in sorted(SCENARIO_SETS_DIR.glob("*.json")):
            try:
                st = load_manifest(f)
                print(f"  {f.name}: {st.n_scenarios} scenarios, mode={st.disturbance_mode}, "
                      f"seed={st.seed_base}, DIST=[{st.dist_min_sys_pu}, {st.dist_max_sys_pu}]")
            except Exception as exc:
                print(f"  {f.name}: load FAILED: {exc}")
    if not (args.regenerate or args.show):
        p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
