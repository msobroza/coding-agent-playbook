"""The verify-pack parts of ``guard_config.json`` rendered at sync (specs/prK-hook-pack.md §E.0.5, §E.2).

- ``prompts``: every resolved prompt's slash mapped to ``{id, output_contract}``,
  so prompt-output-contract-on-stop finds the active prompt's contract without
  reading a prompt file at run time;
- the repository layout tests-with-source-nudge reads. The detector has no
  source-root or test-root fact (SPEC §8.2), so sync derives both once and bakes
  them into that hook's rendered ``config``: the source root is ``src`` when it
  exists, else the repository root (``.``); the test roots are
  ``[tool.pytest.ini_options] testpaths`` when set, else ``tests``.

Both are repo-relative and machine-independent (§D.8.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

    from coding_agent_playbook.types import Prompt

__all__ = [
    "NUDGE_HANDLER",
    "RepoLayout",
    "bake_layout",
    "prompts_table",
    "repo_layout",
]

#: The builtin whose ``stop`` config receives the layout.
NUDGE_HANDLER: Final = "tests_with_source_nudge"
_PYPROJECT_MAX_BYTES: Final = 1024 * 1024


@dataclass(frozen=True)
class RepoLayout:
    """Where a repository keeps its source and its tests, repo-relative (``.`` is the root).

    Example: ``RepoLayout(source_roots=("src",), test_roots=("tests",))``.
    """

    source_roots: tuple[str, ...] = (".",)
    test_roots: tuple[str, ...] = ("tests",)


def repo_layout(repo_root: Path) -> RepoLayout:
    """The layout of ``repo_root``: ``src`` (else ``.``) and pytest ``testpaths`` (else ``tests``).

    An unreadable or malformed ``pyproject.toml`` falls back to ``tests``.

    Example::

        >>> repo_layout(Path("/no/such/repo"))
        RepoLayout(source_roots=('.',), test_roots=('tests',))
    """
    sources = ("src",) if (repo_root / "src").is_dir() else (".",)
    return RepoLayout(source_roots=sources, test_roots=_testpaths(repo_root) or ("tests",))


def bake_layout(record: dict[str, Any], layout: RepoLayout) -> dict[str, Any]:
    """``record`` (a ``ResolvedHook.to_json()``) with the layout in its nudge ``stop`` config.

    Roots the consumer set in ``[hooks.<id>]`` win; any other hook is returned as is.

    Example::

        >>> bake_layout({"handlers": {}}, RepoLayout())
        {'handlers': {}}
    """
    handler = record.get("handlers", {}).get("stop")
    if not isinstance(handler, dict) or handler.get("name") != NUDGE_HANDLER:
        return record
    config = handler.setdefault("config", {})
    config.setdefault("source_roots", list(layout.source_roots))
    config.setdefault("test_roots", list(layout.test_roots))
    return record


def prompts_table(prompts: Iterable[Prompt]) -> dict[str, dict[str, Any]]:
    """``{slash: {"id", "output_contract"}}`` for every prompt; the first prompt per slash wins.

    Example::

        >>> prompts_table([])
        {}
    """
    table: dict[str, dict[str, Any]] = {}
    for prompt in prompts:
        fm = prompt.frontmatter
        table.setdefault(fm.slash, {"id": fm.id, "output_contract": list(fm.output_contract)})
    return table


def _testpaths(repo_root: Path) -> tuple[str, ...]:
    """``[tool.pytest.ini_options] testpaths`` as repo-relative strings, ``()`` when unset."""
    import tomllib

    try:
        with (repo_root / "pyproject.toml").open("rb") as handle:
            data = handle.read(_PYPROJECT_MAX_BYTES + 1)
        if len(data) > _PYPROJECT_MAX_BYTES:
            return ()
        document = tomllib.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return ()
    options = _table(_table(document.get("tool")).get("pytest")).get("ini_options")
    paths = _table(options).get("testpaths")
    if isinstance(paths, str):  # the ini spelling: whitespace-separated
        paths = paths.split()
    if not isinstance(paths, list):
        return ()
    return tuple(p.strip("/") or "." for p in paths if isinstance(p, str) and p.strip())


def _table(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, dict) else {}
