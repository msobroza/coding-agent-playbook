"""A skill section's impact and the priority band it owns (prU D17).

It lives in the artifacts layer because a :class:`MemberReference` carries its
section's impact, and ``artifacts`` may not import ``skills``;
``skills.sections`` parses section entries into it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping


class Impact(StrEnum):
    """A section's impact, declared from most to least important (D17).

    Example: ``Impact("HIGH").band`` -> ``range(40, 60)``.
    """

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    @property
    def band(self) -> range:
        """The priorities a member of a section of this impact may take."""
        return IMPACT_BANDS[self]

    @property
    def rank(self) -> int:
        """0 for CRITICAL up to 3 for LOW: sections are declared in rank order."""
        return list(Impact).index(self)


#: Priority = impact band + rank within the section (D17).
IMPACT_BANDS: Final[Mapping[Impact, range]] = {
    Impact.CRITICAL: range(20, 40),
    Impact.HIGH: range(40, 60),
    Impact.MEDIUM: range(60, 80),
    Impact.LOW: range(80, 100),
}
