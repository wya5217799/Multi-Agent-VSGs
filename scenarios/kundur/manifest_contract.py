from __future__ import annotations

from scenarios.kundur.model_profile import KundurModelProfile


_REQUIRED_KEYS = ("solver", "initialization", "measurement")


def validate_kundur_alignment(profile: KundurModelProfile, manifest: dict) -> list[str]:
    issues: list[str] = []
    missing = [k for k in _REQUIRED_KEYS if k not in manifest]
    if missing:
        return [f"missing required manifest key: {k}" for k in missing]
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
    if profile.solver_family == "sps_phasor":
        pgmode = manifest["solver"].get("powergui_mode", "")
        if pgmode.lower() != "phasor":
            issues.append(f"powergui_mode is '{pgmode}', expected 'Phasor' for sps_phasor")
    if "phase_command_mode" in manifest:
        if manifest["phase_command_mode"] != profile.phase_command_mode:
            issues.append(
                f"phase_command_mode is '{manifest['phase_command_mode']}', "
                f"expected '{profile.phase_command_mode}'"
            )
    return issues
