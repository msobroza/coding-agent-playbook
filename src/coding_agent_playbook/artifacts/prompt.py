"""The Prompt artifact and its frontmatter (SPEC.md §6.6.2).

Markdown round-trip goes through :mod:`coding_agent_playbook.artifacts.frontmatter`.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from coding_agent_playbook.artifacts.frontmatter import (
    _read_markdown,
    _without_empty,
    format_frontmatter,
    frontmatter_keys_problem,
)
from coding_agent_playbook.exit_two import ExitTwoError


class PromptLoadError(ExitTwoError, ValueError):
    """A prompt file whose frontmatter keys cannot become a :class:`Prompt`.

    ``str`` is ``<path>: <problem>``. Raised for an unknown, retired
    (``version``, ``eval_samples``; #281) or missing key, which would otherwise
    surface as a bare dataclass ``TypeError`` naming no file. An
    :class:`ExitTwoError`, so every command prints ``error: <path>: <problem>``
    and exits 2; a ``ValueError``, so the eval prompt renderer's handler keeps
    catching it.

    Example::

        >>> str(PromptLoadError(Path("prompts/x.md"), "unknown frontmatter key 'impact'"))
        "prompts/x.md: unknown frontmatter key 'impact'"
    """

    def __init__(self, path: Path, problem: str) -> None:
        self.path = path
        self.problem = problem
        super().__init__(f"{path}: {problem}")


@dataclass
class PromptFrontmatter:
    id: str
    name: str
    description: str
    slash: str
    applies_if: dict[str, Any] = field(default_factory=dict)
    input_variables: list[dict[str, Any]] = field(default_factory=list)
    includes_rules: list[str] = field(default_factory=list)
    # Regexes the agent's final message must match while this prompt is active
    # (specs/prK-hook-pack.md §E.2 prompt-output-contract-on-stop); compiled by
    # ``playbook validate``, dropped from markdown when empty.
    output_contract: list[str] = field(default_factory=list)
    # Exactly one of {"read_only": True} or {"globs": [...]} (specs/prK-hook-pack.md
    # §E.3). A dict on purpose: ``_without_empty`` drops ``[]``, so an empty-list
    # "read-only" would round-trip to "unrestricted", and a defaulted bool would
    # add ``read_only: false`` to every prompt's markdown.
    write_scope: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # YAML parses 'key:' (blank value) as None; the dataclass default does
        # not fire for an explicit None argument. Coerce so the declared field
        # types hold and markdown round-trip stays lossless (SPEC §6.6.3).
        # This also normalises None passed from Python code: callers should
        # pass {} or [] for "empty/always", never None.
        if self.applies_if is None:
            self.applies_if = {}
        if self.input_variables is None:
            self.input_variables = []
        if self.includes_rules is None:
            self.includes_rules = []
        if self.output_contract is None:
            self.output_contract = []
        if self.write_scope is None:
            self.write_scope = {}


@dataclass
class Prompt:
    frontmatter: PromptFrontmatter
    body: str
    template_body: str
    is_templated: bool
    source_path: Path | None
    source_package: str

    @classmethod
    def from_markdown(cls, path: Path, source_package: str) -> Prompt:
        """Load the prompt at ``path``, raising :class:`PromptLoadError` on a bad key set.

        Example::

            >>> Prompt.from_markdown(Path("playbook/prompts/x.md"), "<repo-local>")  # doctest: +SKIP
        """
        data, body, is_templated = _read_markdown(path)
        problem = frontmatter_keys_problem(data, PromptFrontmatter)
        if problem is not None:
            raise PromptLoadError(path, problem)
        return cls(PromptFrontmatter(**data), body, body, is_templated, path, source_package)

    def to_markdown(self) -> str:
        return format_frontmatter(
            _without_empty(dataclasses.asdict(self.frontmatter)), self.template_body
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frontmatter": dataclasses.asdict(self.frontmatter),
            "body": self.body,
            "template_body": self.template_body,
            "is_templated": self.is_templated,
            "source_path": None if self.source_path is None else str(self.source_path),
            "source_package": self.source_package,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Prompt:
        source_path = data["source_path"]
        return cls(
            PromptFrontmatter(**data["frontmatter"]),
            data["body"],
            data["template_body"],
            data["is_templated"],
            None if source_path is None else Path(source_path),
            data["source_package"],
        )
