"""``playbook validate``'s framework checks (D57, D71, D74, D77; prU L0-19).

- the ``framework`` key names a usable layer, and that layer ships ``framework.toml``;
- at most one framework is enabled (``validation.preflight.framework_conflict``);
- each enabled framework's ``framework.toml`` is sound (``config.framework``);
- each enabled framework's skills tag only the D74 roles, one skill per role
  (``skills.capabilities``); only enabled frameworks' tags are read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.config.framework import (
    FrameworkMetadataError,
    framework_layers,
    read_framework_metadata,
)
from coding_agent_playbook.skills.capabilities import capability_problems
from coding_agent_playbook.validation import preflight as _sync_preflight
from coding_agent_playbook.validation.findings import ValidationError

if TYPE_CHECKING:
    from coding_agent_playbook.artifacts.skill import Skill
    from coding_agent_playbook.config.model import Config

_PATH = "framework"


def check_framework(config: Config, skills: list[Skill]) -> list[ValidationError]:
    """Every framework error of ``config``; ``skills`` are every layer's, unmerged.

    Example::

        >>> check_framework(ctx.config, ctx.artifact_source.list_skills())  # doctest: +SKIP
        []
    """
    errors = _framework_key_errors(config.framework)
    conflict = _sync_preflight.framework_conflict(config.layers_enabled)
    if conflict is not None:
        errors.append(ValidationError(path=_PATH, message=conflict))
    for package in framework_layers(config.layers_enabled):
        errors.extend(_metadata_errors(package))
        errors.extend(
            ValidationError(path=f"{package} skills/{skill_id}", message=problem)
            for skill_id, problem in capability_problems(skills, package)
        )
    return errors


def _framework_key_errors(framework: str | None) -> list[ValidationError]:
    """The ``framework`` key's layer is unusable, or is not a framework."""
    return [
        ValidationError(path=_PATH, message=problem)
        for problem in _sync_preflight.framework_choice_problems(framework)
    ]


def _metadata_errors(package: str) -> list[ValidationError]:
    """One error per problem in ``package``'s ``framework.toml``."""
    try:
        read_framework_metadata(package)
    except FrameworkMetadataError as exc:
        return [ValidationError(path=exc.where, message=problem) for problem in exc.problems]
    return []
