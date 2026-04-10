"""Tests for lazy backend imports in plotting/evaluation helpers."""

import importlib


def test_plotting_configs_import_without_andes_installed():
    """Importing plotting.configs should not eagerly import optional backends."""
    module = importlib.import_module("plotting.configs")
    assert hasattr(module, "SCENARIOS")
    assert hasattr(module, "resolve_env_class")
