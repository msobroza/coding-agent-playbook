"""Release version rules: tag names, the minor floor and an explicit version's check.

Release tags are ``v<version>`` (commitizen ``tag_format = "v$version"``). A
release whose graded set changed must be at least a minor (ADR 0012), whatever
the Conventional Commit types since the last tag say.
"""

from __future__ import annotations

import re
from typing import Final

from packaging.version import InvalidVersion, Version

__all__ = [
    "TAG_PREFIX",
    "VersionError",
    "check_next_version",
    "is_release_tag",
    "raises_minor",
    "release_tag",
]

TAG_PREFIX: Final = "v"
_RELEASE_TAG: Final = re.compile(r"^v\d+\.\d+\.\d+$")


class VersionError(ValueError):
    """A version string that is not a valid next release."""


def release_tag(version: str) -> str:
    """The git tag of release ``version``.

    Example::

        >>> release_tag("9.9.9")
        'v9.9.9'
    """
    return f"{TAG_PREFIX}{version}"


def is_release_tag(name: str) -> bool:
    """Whether ``name`` is a final release tag (``vX.Y.Z``; no pre-releases).

    Example::

        >>> is_release_tag("v9.9.9"), is_release_tag("v9.9.9a0"), is_release_tag("9.9.9")
        (True, False, False)
    """
    return _RELEASE_TAG.match(name) is not None


def raises_minor(current: str, proposed: str) -> bool:
    """Whether ``proposed`` moves the major or minor number of ``current``.

    Example::

        >>> raises_minor("9.9.9", "9.9.10"), raises_minor("9.9.9", "9.10.0")
        (False, True)
    """
    now, then = _parse(current), _parse(proposed)
    return (then.major, then.minor) > (now.major, now.minor)


def check_next_version(current: str, proposed: str) -> str:
    """``proposed`` normalized, when it is a final ``X.Y.Z`` release above ``current``.

    Raises :class:`VersionError` naming both versions otherwise.

    Example::

        >>> check_next_version("9.9.9a0", "9.9.9")
        '9.9.9'
    """
    then = _parse(proposed)
    if then.is_prerelease or then.is_devrelease or len(then.release) != 3:
        raise VersionError(f"version {proposed!r} is not a final X.Y.Z release")
    if then <= _parse(current):
        raise VersionError(f"version {proposed!r} is not above the current version {current!r}")
    return str(then)


def _parse(version: str) -> Version:
    try:
        return Version(version)
    except InvalidVersion as exc:
        raise VersionError(f"{version!r} is not a PEP 440 version") from exc
