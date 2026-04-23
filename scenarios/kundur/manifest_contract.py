from __future__ import annotations

from scenarios.kundur.model_profile import KundurModelProfile


def validate_kundur_alignment(profile: KundurModelProfile, manifest: dict) -> list[str]:
    issues: list[str] = []
    if manifest["solver"]["family"] != profile.solver_family:
        issues.append("solver_family mismatch")
    if manifest["measurement"]["mode"] != profile.pe_measurement:
        issues.append("pe_measurement mismatch")
    if manifest["initialization"]["warmup_mode"] != profile.warmup_mode:
        issues.append("warmup_mode mismatch")
    if not profile.feature_flags.allow_pref_ramp and manifest["initialization"]["uses_pref_ramp"]:
        issues.append("pref_ramp present while profile forbids it")
    if not profile.feature_flags.allow_simscape_solver_config and manifest["solver"]["has_solver_config"]:
        issues.append("solver_config present while profile forbids it")
    return issues
