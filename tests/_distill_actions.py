"""Cross-check the mapping specs' ``distill`` actions against ``ATTRIBUTIONS.md`` (D78(15)).

A mapping spec (``specs/prU-core-python-skills/mapping-<skill>.md``) gives each rule
an action; a rule it distills is written fresh and holds no upstream text, so
``catalog/core/ATTRIBUTIONS.md`` (parsed by ``tests/_attributions.py``) must never
map upstream text to it.

Example: ``"rules/python-comments-why.md" in distill_actions()["python-coding"]`` -> ``True``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from tests._attributions import vendored_targets
from tests._catalog import REPO_ROOT

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping
    from pathlib import Path

    from tests._attributions import Attributions

#: The mapping action (D78(15)) of a rule written fresh, with no vendored text.
DISTILL: Final = "distill"
#: The per-skill mapping specs (``mapping-<skill>.md``) that name each rule's action.
MAPPING_SPECS_DIR: Final = REPO_ROOT / "specs" / "prU-core-python-skills"

#: A mapping spec's rule table: ``| `rules/<file>` | section | priority | action | ...``.
_SPEC_RULE_ROW_RE: Final = re.compile(r"^\| `(rules/[^`]+)` \|[^|]*\|[^|]*\| (\S+) \|")


def distill_actions(spec_dir: Path = MAPPING_SPECS_DIR) -> dict[str, frozenset[str]]:
    """Skill -> the rule files its ``mapping-<skill>.md`` gives the ``distill`` action (D78(15)).

    Example: ``"rules/python-comments-why.md" in distill_actions()["python-coding"]`` -> ``True``.
    """
    actions: dict[str, frozenset[str]] = {}
    for spec in sorted(spec_dir.glob("mapping-*.md")):
        rows = (_SPEC_RULE_ROW_RE.match(line) for line in spec.read_text("utf-8").splitlines())
        skill = spec.stem.removeprefix("mapping-")
        actions[skill] = frozenset(row.group(1) for row in rows if row and row[2] == DISTILL)
    return actions


def distill_action_errors(
    parsed: Attributions, actions: Mapping[str, Collection[str]]
) -> list[str]:
    """Every rule the mapping spec distills that ATTRIBUTIONS.md maps with a change list (D78(15)).

    A distilled rule holds no upstream text, so it is listed as distilled or
    engine-written, never as a table row's target; a ``.md.j2`` target matches its
    ``.md`` spec name.
    """
    errors = []
    for skill, paths in sorted(actions.items()):
        targets = {t.removesuffix(".j2") for t in vendored_targets(parsed, skill)}
        errors += [
            f"{skill}/{path}: the mapping spec distills it, "
            "but a table row maps upstream text to it"
            for path in sorted(paths)
            if path in targets
        ]
    return errors
