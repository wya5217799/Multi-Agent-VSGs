# FACT: 这是合约本身。loader 解析逻辑 + on-disk JSON manifest = 训练/评估时 ODE
# scenario 的真值。docstring 与 commit message 是 CLAIM。
# 详见 docs/EVIDENCE_PROTOCOL.md。

"""ODE Scenario value-object + on-disk manifest (Plan 2026-05-02 Stage 2).

Paper Sec.IV-A: 100 train + 50 test scenarios. Cumulative-reward comparison
is reproducible only if the test set is fixed.

This module is the ODE-side counterpart of `scenarios/kundur/scenario_loader.py`
(Simulink-side). Distinct from that module because:

  - ODE has no concept of R-block / pm_step_proxy / CCS proxies.
  - Disturbance enters Eq.4 directly as `Δu ∈ R^N` (per-bus equivalent).
  - No SG/load-bus distinction at the ODE abstraction level.

Hard boundaries (D2 additive-extension contract, see
`docs/paper/ode_paper_alignment_deviations.md`):

  - This module is read-only data + frozen dataclass; **does NOT** import or
    mutate `MultiVSGEnv`. Wiring into env reset is in `multi_vsg_env.py::reset()`.
  - Caller signature in `train_ode.py` may legacy-use tuple-shape; this module
    provides a `to_legacy_tuple()` helper for incremental migration.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

import config as cfg

# Repo-relative paths
REPO_ROOT = Path(__file__).resolve().parents[2]
ODE_SCENARIO_SETS_DIR = REPO_ROOT / "scenarios" / "kundur" / "ode_scenario_sets"

# Paper-explicit set sizes (Sec.IV-A).
N_TRAIN_PAPER: int = 100
N_TEST_PAPER: int = 50

# Distinct seeds: train and test must NOT collide.
SEED_TRAIN_DEFAULT: int = 42
SEED_TEST_DEFAULT: int = 99   # matches historical TEST_SEED in evaluate_ode.py


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ODEScenario:
    """One ODE-side disturbance scenario.

    Fields:
        scenario_idx: 0-based index within the set.
        delta_u: per-bus equivalent disturbance, shape (N,). Enters Eq.4
                 directly as the static `Δu` term applied at reset.
        comm_failed_links: list of (i, j) tuples whose link is forced
                           failed for this scenario. Empty by default.
        seed_base: rng seed that originally generated this scenario.
                   Stored for traceability, not used at runtime.
    """

    scenario_idx: int
    delta_u: tuple[float, ...]
    comm_failed_links: tuple[tuple[int, int], ...] = field(default_factory=tuple)
    seed_base: int = 0

    def to_legacy_tuple(self) -> tuple[np.ndarray, list[tuple[int, int]] | None]:
        """Translate to the (delta_u, failed_links) shape used by legacy
        train_ode.py / evaluate_ode.py inline scenario lists."""
        du = np.asarray(self.delta_u, dtype=np.float64)
        fl: list[tuple[int, int]] | None = (
            [tuple(p) for p in self.comm_failed_links] if self.comm_failed_links else None
        )
        return du, fl


@dataclass
class ODEScenarioSet:
    """A complete fixed scenario set (train or test)."""

    schema_version: int
    name: str
    n_scenarios: int
    seed_base: int
    n_agents: int
    dist_min_pu: float
    dist_max_pu: float
    comm_fail_prob: float
    scenarios: list[ODEScenario]


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


def generate_scenarios(
    n: int,
    seed_base: int,
    name: str,
    n_agents: Optional[int] = None,
    dist_min_pu: Optional[float] = None,
    dist_max_pu: Optional[float] = None,
    comm_fail_prob: Optional[float] = None,
    comm_adjacency: Optional[dict[int, list[int]]] = None,
) -> ODEScenarioSet:
    """Deterministic ODE scenario generator.

    Replicates the inline logic that lived in
    ``scenarios/kundur/train_ode.py::generate_scenario_set`` and
    ``scenarios/kundur/evaluate_ode.py::generate_test_scenarios`` so the
    on-disk JSON is byte-equal to historical inline-generated tuples
    (modulo dataclass packaging) when called with the same seed.

    Defaults pull from ``config.py`` to preserve historical behaviour;
    callers can override for experiments.
    """
    n_agents = n_agents if n_agents is not None else cfg.N_AGENTS
    dist_min_pu = dist_min_pu if dist_min_pu is not None else float(cfg.DISTURBANCE_MIN)
    dist_max_pu = dist_max_pu if dist_max_pu is not None else float(cfg.DISTURBANCE_MAX)
    comm_fail_prob = comm_fail_prob if comm_fail_prob is not None else float(cfg.COMM_FAIL_PROB)
    if comm_adjacency is None:
        comm_adjacency = cfg.COMM_ADJACENCY

    rng = np.random.default_rng(seed_base)
    scenarios: list[ODEScenario] = []
    for k in range(n):
        # Disturbance: 1-2 random buses, signed magnitude.
        n_disturbed = int(rng.integers(1, 3))
        buses = rng.choice(n_agents, size=n_disturbed, replace=False)
        delta_u = np.zeros(n_agents)
        for bus in buses:
            mag = float(rng.uniform(dist_min_pu, dist_max_pu))
            sign = float(rng.choice([-1, 1]))
            delta_u[bus] = sign * mag

        # Communication link failures (mirrors legacy generator semantics:
        # only adjacent neighbour pairs may fail; failure is bidirectional).
        failed_links: list[tuple[int, int]] = []
        for i, neighbors in comm_adjacency.items():
            for j in neighbors:
                if (j, i) not in failed_links and rng.random() < comm_fail_prob:
                    failed_links.append((int(i), int(j)))
                    failed_links.append((int(j), int(i)))

        scenarios.append(
            ODEScenario(
                scenario_idx=k,
                delta_u=tuple(float(x) for x in delta_u),
                comm_failed_links=tuple(tuple(int(x) for x in p) for p in failed_links),
                seed_base=int(seed_base),
            )
        )

    return ODEScenarioSet(
        schema_version=1,
        name=name,
        n_scenarios=n,
        seed_base=int(seed_base),
        n_agents=int(n_agents),
        dist_min_pu=float(dist_min_pu),
        dist_max_pu=float(dist_max_pu),
        comm_fail_prob=float(comm_fail_prob),
        scenarios=scenarios,
    )


# ---------------------------------------------------------------------------
# Serialize / deserialize
# ---------------------------------------------------------------------------


def serialize(s: ODEScenarioSet) -> dict:
    return {
        "schema_version": s.schema_version,
        "name": s.name,
        "n_scenarios": s.n_scenarios,
        "seed_base": s.seed_base,
        "n_agents": s.n_agents,
        "dist_min_pu": s.dist_min_pu,
        "dist_max_pu": s.dist_max_pu,
        "comm_fail_prob": s.comm_fail_prob,
        "scenarios": [
            {
                "scenario_idx": x.scenario_idx,
                "delta_u": list(x.delta_u),
                "comm_failed_links": [list(p) for p in x.comm_failed_links],
                "seed_base": x.seed_base,
            }
            for x in s.scenarios
        ],
    }


def deserialize(d: dict) -> ODEScenarioSet:
    if d.get("schema_version") != 1:
        raise ValueError(f"unsupported schema_version {d.get('schema_version')}")
    scenarios = [
        ODEScenario(
            scenario_idx=int(x["scenario_idx"]),
            delta_u=tuple(float(y) for y in x["delta_u"]),
            comm_failed_links=tuple(tuple(int(z) for z in p) for p in x.get("comm_failed_links", [])),
            seed_base=int(x.get("seed_base", 0)),
        )
        for x in d["scenarios"]
    ]
    return ODEScenarioSet(
        schema_version=int(d["schema_version"]),
        name=str(d["name"]),
        n_scenarios=int(d["n_scenarios"]),
        seed_base=int(d["seed_base"]),
        n_agents=int(d["n_agents"]),
        dist_min_pu=float(d["dist_min_pu"]),
        dist_max_pu=float(d["dist_max_pu"]),
        comm_fail_prob=float(d["comm_fail_prob"]),
        scenarios=scenarios,
    )


def save_manifest(s: ODEScenarioSet, path: Path | str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as f:
        json.dump(serialize(s), f, indent=2)


def load_manifest(path: Path | str) -> ODEScenarioSet:
    with Path(path).open("r", encoding="utf-8") as f:
        return deserialize(json.load(f))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _regenerate_default_manifests() -> None:
    """Materialize the canonical ODE train + test sets."""
    train_path = ODE_SCENARIO_SETS_DIR / "kd_train_100.json"
    test_path = ODE_SCENARIO_SETS_DIR / "kd_test_50.json"

    train = generate_scenarios(N_TRAIN_PAPER, SEED_TRAIN_DEFAULT, "kd_train_100")
    test = generate_scenarios(N_TEST_PAPER, SEED_TEST_DEFAULT, "kd_test_50")

    save_manifest(train, train_path)
    save_manifest(test, test_path)
    print(f"  wrote {train_path}  ({train.n_scenarios} scenarios)")
    print(f"  wrote {test_path}   ({test.n_scenarios} scenarios)")

    # Sanity print
    print("  train[0..2]:", [
        f"|du|={np.linalg.norm(s.delta_u):.3f} fl={len(s.comm_failed_links)//2}"
        for s in train.scenarios[:3]
    ])
    print("  test[0..2]: ", [
        f"|du|={np.linalg.norm(s.delta_u):.3f} fl={len(s.comm_failed_links)//2}"
        for s in test.scenarios[:3]
    ])


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="ODE scenario manifest generator")
    p.add_argument("--regenerate", action="store_true",
                   help="(Re)generate canonical kd_train_100 + kd_test_50 manifests.")
    p.add_argument("--show", action="store_true",
                   help="Show summary of existing manifests.")
    args = p.parse_args()

    if args.regenerate:
        print("Regenerating ODE scenario manifests ...")
        _regenerate_default_manifests()
    if args.show:
        for f in sorted(ODE_SCENARIO_SETS_DIR.glob("*.json")):
            try:
                s = load_manifest(f)
                print(
                    f"  {f.name}: {s.n_scenarios} scen, seed={s.seed_base}, "
                    f"DIST=[{s.dist_min_pu}, {s.dist_max_pu}], comm_p={s.comm_fail_prob}"
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  {f.name}: load FAILED: {exc}")
    if not (args.regenerate or args.show):
        p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
