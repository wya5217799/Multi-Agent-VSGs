"""Canonical source for Kundur initial conditions.

Single-source loader for kundur_ic.json.  All callers (build script,
config, env reset) must go through this module — no direct jsondecode.

Constraint: must NOT import scenarios.kundur.config_simulink.  All
VSG-base → system-base conversions are done by the caller, who passes
vsg_sn_mva and sbase_mva explicitly.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

_DEFAULT_JSON_PATH = Path(__file__).parent / "kundur_ic.json"

_VALID_CALIBRATION_STATUSES = frozenset({
    "placeholder_pre_impedance_fix",
    "calibrated",
})
_SOURCE_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# Source: build_powerlib_kundur.m vlf_ess(:,2) — VSG rotor angle ICs [deg]
_DELTA0_DEG_DEFAULT: tuple[float, ...] = (18.0, 10.0, 7.0, 12.0)


@dataclass(frozen=True)
class KundurIC:
    """Validated snapshot of Kundur VSG initial conditions.

    All values are in VSG-base pu (200 MVA).  Call to_sbase_pu() to
    convert to system-base pu for use in Python training code.
    """

    schema_version: int
    calibration_status: str
    vsg_p0_vsg_base_pu: tuple[float, ...]
    source_hash: str
    vsg_delta0_deg: tuple[float, ...] = _DELTA0_DEG_DEFAULT

    def __post_init__(self) -> None:
        errors: list[str] = []

        if self.schema_version != 1:
            errors.append(f"schema_version must be 1, got {self.schema_version}")

        if self.calibration_status not in _VALID_CALIBRATION_STATUSES:
            errors.append(
                f"calibration_status={self.calibration_status!r} not in "
                f"{sorted(_VALID_CALIBRATION_STATUSES)}"
            )

        if len(self.vsg_p0_vsg_base_pu) != 4:
            errors.append(
                f"vsg_p0_vsg_base_pu must have length 4, got {len(self.vsg_p0_vsg_base_pu)}"
            )
        else:
            for idx, v in enumerate(self.vsg_p0_vsg_base_pu):
                if not isinstance(v, float):
                    errors.append(
                        f"vsg_p0_vsg_base_pu[{idx}] must be float, got {type(v).__name__}"
                    )
                elif v <= 0.0:
                    errors.append(f"vsg_p0_vsg_base_pu[{idx}]={v} must be positive")

        if not _SOURCE_HASH_RE.match(self.source_hash):
            errors.append(
                f"source_hash={self.source_hash!r} must match sha256:<64-hex-chars>"
            )

        if len(self.vsg_delta0_deg) != 4:
            errors.append(
                f"vsg_delta0_deg must have length 4, got {len(self.vsg_delta0_deg)}"
            )
        else:
            arr = np.asarray(self.vsg_delta0_deg, dtype=np.float64)
            if not np.isfinite(arr).all():
                errors.append(
                    f"vsg_delta0_deg: all values must be finite, got {list(self.vsg_delta0_deg)}"
                )

        if errors:
            raise ValueError(
                "KundurIC validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

    def to_sbase_pu(self, *, vsg_sn_mva: float, sbase_mva: float) -> np.ndarray:
        """Convert vsg_p0 from VSG-base pu to system-base pu.

        Args:
            vsg_sn_mva: VSG rated power in MVA (200.0 for Kundur)
            sbase_mva:  System base in MVA (100.0 for Kundur)

        Returns:
            shape (4,) array in system-base pu
        """
        arr = np.asarray(self.vsg_p0_vsg_base_pu, dtype=np.float64)
        return arr * (vsg_sn_mva / sbase_mva)


def load_kundur_ic(path: str | Path | None = None) -> KundurIC:
    """Load and validate kundur_ic.json.

    Args:
        path: override path to the JSON file.  Defaults to the canonical
              kundur_ic.json next to this module.

    Returns:
        Validated KundurIC instance.

    Raises:
        FileNotFoundError: if the JSON file does not exist.
        ValueError: if schema validation fails.
    """
    json_path = Path(path) if path is not None else _DEFAULT_JSON_PATH
    if not json_path.exists():
        raise FileNotFoundError(
            f"kundur_ic.json not found at {json_path}. "
            "Run build_powerlib_kundur.m or restore from git."
        )

    raw = json_path.read_text(encoding="utf-8")
    data = json.loads(raw)

    units = data.get("units", {})
    if units.get("vsg_p0_vsg_base_pu") != "pu_on_vsg_base":
        raise ValueError(
            f"units.vsg_p0_vsg_base_pu must be 'pu_on_vsg_base', "
            f"got {units.get('vsg_p0_vsg_base_pu')!r}"
        )

    delta0_raw = data.get("vsg_delta0_deg")
    vsg_delta0_deg = (
        tuple(float(v) for v in delta0_raw) if delta0_raw is not None
        else _DELTA0_DEG_DEFAULT
    )

    return KundurIC(
        schema_version=int(data["schema_version"]),
        calibration_status=str(data["calibration_status"]),
        vsg_p0_vsg_base_pu=tuple(float(v) for v in data["vsg_p0_vsg_base_pu"]),
        source_hash=str(data["source_hash"]),
        vsg_delta0_deg=vsg_delta0_deg,
    )
