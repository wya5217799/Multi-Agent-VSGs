"""Repair hint generation for harness diagnostics.

``generate_repair_hints`` maps raw MATLAB/Simulink error strings to
structured hints that an agent can use when deciding how to call
``harness_model_patch_verify``.

Design constraints:
- Hints are heuristic suggestions, not guaranteed-correct patches.
- Returns an empty list when no known pattern matches — never blocks.
- Rules are keyed by the hint_id from the simulink_debug knowledge base (D1-D6).
- Each rule fires at most once per call (deduplication built-in).
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Rule table — one entry per known pattern (D1-D6 from simulink_debug.md)
# ---------------------------------------------------------------------------
# Each rule:
#   keywords    : list of lowercase substrings; ANY match triggers the rule
#   suggested_action : human-readable repair suggestion for the agent
#   rationale   : why this rule exists (links to knowledge base entry)

_RULES: list[dict[str, Any]] = [
    {
        "hint_id": "D1",
        "keywords": ["transitiontimes"],
        "suggested_action": (
            "Replace deprecated Breaker parameter 'TransitionTimes' with 'SwitchTimes'. "
            "Also check InitialState ('open'/'closed'), BreakerResistance, "
            "SnubberResistance (1e6 not 'inf'), SnubberCapacitance ('inf' not '0')."
        ),
        "rationale": "R2025b breaking change: Breaker parameter names renamed (simulink_debug D1).",
    },
    {
        "hint_id": "D2",
        "keywords": [
            "failed to converge",
            "initial conditions failed",
            "初始条件",
            "无法满足所有初始条件",
            "vfd",
            "vfd_g",
            ".p.v",
            "域参考模块",
            "vmag0",
        ],
        "suggested_action": (
            "Check four known causes: (1) Vmag0=0 not set; "
            "(2) damper winding resistance is Inf — use 1e6; "
            "(3) single machine with no load — add at least 1 MW resistive load; "
            "(4) excitation circuit has no grounded reference — add Electrical Reference "
            "to both Vfd/n and SM/fd_n."
        ),
        "rationale": "SM IC solver needs Vmag0, finite damper resistance, real load, and excitation GND (simulink_debug D2).",
    },
    {
        "hint_id": "D3",
        "keywords": [
            "cannot add connection",
            "addconnection",
            "domain mismatch",
            "点输入域不匹配",
            "stator",
            "composite port",
        ],
        "suggested_action": (
            "SM stator composite port cannot be wired directly with add_line or addConnection. "
            "Expand SM ports (port_option='ee.enum.threePhasePort.expanded'), "
            "then use a Phase Splitter block to bridge individual a/b/c ports to composite downstream blocks."
        ),
        "rationale": "SM stator machine-class port incompatible with network composite ports (simulink_debug D3).",
    },
    {
        "hint_id": "D4",
        "keywords": [
            "synchronousmachineinit",
            "mechanical port",
            "port r",
            "sm/r",
        ],
        "suggested_action": (
            "Connect SM mechanical port R to a TorqueSource and port C to MechRef. "
            "An unconnected mechanical port causes SynchronousMachineInit.p internal crash."
        ),
        "rationale": "SM mechanical ports must be connected before initialization (simulink_debug D4).",
    },
    {
        "hint_id": "D5",
        "keywords": [
            "matlabcallerror",
            "eval() failed",
            "engine disconnected",
            "引擎断连",
        ],
        "suggested_action": (
            "MATLAB engine entered an error state. The session will auto-reconnect. "
            "Re-run the failed task; if it fails again inspect the underlying MATLAB error message."
        ),
        "rationale": "MATLAB eval() errors can orphan the engine session; matlab_session.py handles reconnect (simulink_debug D5).",
    },
    {
        "hint_id": "D6",
        "keywords": [
            "steadystate",
            "second solve",
            "second time",
            "第二次求解",
            "round_rotor",
        ],
        "suggested_action": (
            "Multi-machine steadystate IC warnings are usually harmless — "
            "Simulink falls back to approximate IC and the simulation converges dynamically. "
            "Verify that omega settles to ~1.0 pu during the first few seconds. "
            "To suppress, provide Vang0 in the steadystate set_param call."
        ),
        "rationale": "Multi-machine steadystate IC solver needs Vang0 to fully converge; fallback IC is acceptable (simulink_debug D6).",
    },
]


def generate_repair_hints(error_texts: list[str]) -> list[dict[str, Any]]:
    """Match error strings against known patterns and return repair hints.

    Parameters
    ----------
    error_texts:
        Flat list of error/warning message strings from compile_diagnostics
        and step_diagnostics.

    Returns
    -------
    List of repair hint dicts, one per matched rule.  Empty when no pattern
    matches.  Each dict has keys:
        hint_id, match_confidence, evidence, suggested_action, rationale
    """
    if not error_texts:
        return []

    combined_lower = "\n".join(error_texts).lower()
    hints: list[dict[str, Any]] = []

    for rule in _RULES:
        matched_keywords = [kw for kw in rule["keywords"] if kw in combined_lower]
        if not matched_keywords:
            continue

        # Collect the original error strings that triggered at least one keyword.
        evidence = [
            text for text in error_texts
            if any(kw in text.lower() for kw in matched_keywords)
        ]

        confidence: str = "high" if len(matched_keywords) >= 2 else "low"

        hints.append(
            {
                "hint_id": rule["hint_id"],
                "match_confidence": confidence,
                "evidence": evidence,
                "suggested_action": rule["suggested_action"],
                "rationale": rule["rationale"],
            }
        )

    return hints
