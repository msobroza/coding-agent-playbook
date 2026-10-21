"""``playbook check``'s framework lines: the enabled framework and its role map (D57, D77).

One line per enabled framework (validate refuses more than one), for example
``framework mattpocock: clarify -> grill-me, debug -> diagnosing-bugs``; without
one, ``Framework: none``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.config.framework import (
    NO_FRAMEWORK,
    FrameworkMetadataError,
    framework_layers,
    read_framework_metadata,
)
from coding_agent_playbook.skills.capabilities import format_role_map, framework_role_map

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.artifacts.skill import Skill


def format_framework_lines(layers: Sequence[str], skills: Sequence[Skill]) -> list[str]:
    """The indented Environment lines for the frameworks among ``layers``.

    Example::

        >>> format_framework_lines([], [])
        ['  Framework: none']
    """
    packages = framework_layers(layers)
    if not packages:
        return [f"  Framework: {NO_FRAMEWORK}"]
    return [
        f"  {format_role_map(_framework_name(package), framework_role_map(skills, package))}"
        for package in packages
    ]


def _framework_name(package: str) -> str:
    """``framework.toml``'s ``name``; the package when the file is unreadable (validate says why)."""
    try:
        metadata = read_framework_metadata(package)
    except FrameworkMetadataError:
        return package
    return package if metadata is None else metadata.name
