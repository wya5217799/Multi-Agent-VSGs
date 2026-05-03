"""Subset-spec parsing for P2 dispatch filtering (Module α).

``_parse_subset_spec(spec, valid_targets)`` accepts a comma-separated string
of integer indices OR dispatch names (or a mix) and returns the canonical
name tuple.  Used by ``__main__.py`` (CLI) and
``_dynamics._apply_dispatch_subset`` (runtime filter).
"""
from __future__ import annotations


def _parse_subset_spec(spec: str, valid_targets: list[str]) -> tuple[str, ...]:
    """Parse a subset spec string into a canonical tuple of target names.

    Parameters
    ----------
    spec:
        Comma-separated tokens, each either an integer index into
        *valid_targets* or a name present in *valid_targets*.  Mixing is
        allowed (e.g. ``"0,b"``).
    valid_targets:
        Ordered list of target names against which indices and names are
        resolved.

    Returns
    -------
    tuple[str, ...]
        Deduplicated, order-preserved canonical name tuple.

    Raises
    ------
    SystemExit
        On any invalid index or unrecognised name.
    """
    if not spec or not spec.strip():
        raise SystemExit("--dispatch-subset: empty spec")

    tokens = [t.strip() for t in spec.split(",") if t.strip()]
    result: list[str] = []
    seen: set[str] = set()

    for token in tokens:
        # Try to interpret as integer index first.
        try:
            idx = int(token)
        except ValueError:
            idx = None  # type: ignore[assignment]

        if idx is not None:
            if idx < 0 or idx >= len(valid_targets):
                raise SystemExit(
                    f"--dispatch-subset: index {idx!r} out of range "
                    f"(valid_targets has {len(valid_targets)} entries, "
                    f"indices 0..{len(valid_targets) - 1})"
                )
            name = valid_targets[idx]
        else:
            if token not in valid_targets:
                raise SystemExit(
                    f"--dispatch-subset: name {token!r} not in valid_targets "
                    f"({valid_targets!r})"
                )
            name = token

        if name not in seen:
            result.append(name)
            seen.add(name)

    return tuple(result)
