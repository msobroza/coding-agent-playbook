"""Every ``STAGE_FACTORIES`` row names a module and a callable that exist.

The Stop coordinator imports a stage's module from this string table only when the
stage runs (stop_ci_parity_gate._factory), so a moved or renamed stage module
would surface as a failing Stop stage in a consumer session, never in an import.
"""

from __future__ import annotations

import importlib
import importlib.util

import pytest

from coding_agent_playbook.hook_runtime.handlers.stop_ci_parity_gate import STAGE_FACTORIES
from coding_agent_playbook.hook_runtime.registry import _BUILTIN_HANDLER_MODULES


@pytest.mark.parametrize(("stage", "target"), sorted(STAGE_FACTORIES.items()))
def test_every_stage_factory_resolves(stage: str, target: str) -> None:
    module, _, attr = target.partition(":")

    factory = getattr(importlib.import_module(module), attr, None)

    assert callable(factory), f"stage {stage!r}: {target!r} does not resolve"


@pytest.mark.parametrize(("name", "module"), sorted(_BUILTIN_HANDLER_MODULES.items()))
def test_every_builtin_handler_module_resolves(name: str, module: str) -> None:
    # The registry imports these lazily by string, so a moved handler fails only
    # when its hook first fires; find_spec checks the path without importing it.
    assert importlib.util.find_spec(module) is not None, f"{name!r}: {module!r} does not resolve"
