"""dependency-allowlist-guard's tiers over one request (specs/prK-hook-pack.md §E.4).

The handler (``dependencies``) finds the requests; this module judges them,
and ``playbook check-deps`` reuses the allowlist and index rules, so the hook
and its twin never disagree:

- (a) :func:`mismatch`: the wrong installer for ``facts.package_manager``,
  with the corrected command;
- the overlay ``required_index`` and (d) index mixing: :func:`index_finding`;
- the overlay ``allowlist`` (``difflib`` hints, imported on that branch only)
  and (b) new names: :func:`name_findings`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook._pep503 import canonical_name
from coding_agent_playbook.hook_runtime._hosts import url_host
from coding_agent_playbook.hook_runtime.caps import clean_text, clip, quote_data
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.handlers._install_cmds import DEFAULT_INDEXES

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.hook_runtime.handlers._install_cmds import Index, InstallRequest

__all__ = [
    "NEW_DEPENDENCY",
    "NEW_DEPENDENCY_REASON",
    "DependencyPolicy",
    "Finding",
    "adding_line",
    "dependency_policy",
    "index_finding",
    "label",
    "mismatch",
    "name_findings",
]

#: Tier (b)'s rule id and its reason after the names (the generate-tests prompt's own rule).
NEW_DEPENDENCY: Final = "new_dependency"
NEW_DEPENDENCY_REASON: Final = "The playbook says don't add new dependencies without asking."
#: manager -> (the adders that are right, the correction, the dev correction).
_CORRECTIONS: Final[Mapping[str, tuple[frozenset[str], str, str]]] = {
    "uv": (frozenset({"uv"}), "run `uv add {names}`", "run `uv add --dev {names}`"),
    "poetry": (
        frozenset({"poetry"}),
        "run `poetry add {names}`",
        "run `poetry add --group dev {names}`",
    ),
    "pip-tools": (
        frozenset(),
        "add {names} to requirements.in, then run `pip-compile`",
        "add {names} to requirements-dev.in, then run `pip-compile`",
    ),
}
_SHOWN_NAMES: Final = 5


@dataclass(frozen=True, slots=True)
class DependencyPolicy:
    """What the guard enforces: the repo's facts plus the merged hook config.

    Example: ``DependencyPolicy("uv", frozenset({"requests"}), (), "", Decision.ASK)``.
    """

    manager: str | None
    declared: frozenset[str]
    allowlist: tuple[str, ...]
    required_index: str
    index_mode: Decision


@dataclass(frozen=True, slots=True)
class Finding:
    """One tier's verdict: its reason lines, or (tier b) the new names, deduped by the caller.

    Example: ``Finding(Decision.DENY, "lockfile_edit", ("uv.lock is generated ...",))``.
    """

    decision: Decision
    rule: str
    lines: tuple[str, ...] = ()
    names: tuple[str, ...] = ()


def dependency_policy(facts: object, config: Mapping[str, object]) -> DependencyPolicy:
    """The policy of the rendered ``facts`` table and the hook's merged config.

    ``index_mode`` is the stricter of ``index_mode`` and ``mode`` (the
    ``[guardrails.dependencies]`` spelling, merged in by sync).

    Example::

        >>> dependency_policy({"package_manager": "uv"}, {"index_mode": "ask"}).manager
        'uv'
    """
    table = facts if isinstance(facts, dict) else {}
    declared = [*_strings(table.get("dependencies")), *_strings(table.get("dev_dependencies"))]
    required = config.get("required_index")
    manager = table.get("package_manager")
    allowlist = (canonical_name(name) for name in _strings(config.get("allowlist")))
    strict = "deny" in (config.get("index_mode"), config.get("mode"))
    return DependencyPolicy(
        manager=manager if isinstance(manager, str) else None,
        declared=frozenset(canonical_name(name) for name in declared),
        allowlist=tuple(dict.fromkeys(allowlist)),
        required_index=required.rstrip("/") if isinstance(required, str) else "",
        index_mode=Decision.DENY if strict else Decision.ASK,
    )


def mismatch(request: InstallRequest, policy: DependencyPolicy) -> Finding | None:
    """Tier (a): ``request`` adds through the wrong manager; deny naming the right command.

    Example::

        >>> mismatch(pip_install_requests, uv_policy).lines[0]  # doctest: +SKIP
        'This repository uses uv: run `uv add requests` instead of `pip install`.'
    """
    rows = _CORRECTIONS.get(policy.manager or "")
    if rows is None or request.adder is None or request.adder in rows[0] or not request.names:
        return None
    names = " ".join(request.names[:_SHOWN_NAMES])
    correction = (rows[2] if request.dev else rows[1]).format(names=names)
    lines = (
        f"This repository uses {policy.manager}: {correction} instead of `{request.tool}`.",
        "The wrong installer leaves the manifest and the lockfile out of date.",
    )
    return Finding(Decision.DENY, "package_manager_mismatch", lines)


def index_finding(
    indexes: Sequence[Index], policy: DependencyPolicy, *, via: str
) -> Finding | None:
    """The overlay ``required_index`` (deny), else tier (d) index mixing (``index_mode``).

    Example::

        >>> index_finding([("extra", "https://download.pytorch.org/whl/cu121")], policy,
        ...               via="pip install").rule  # doctest: +SKIP
        'index_mixing'
    """
    if policy.required_index:
        other = next((u for _, u in indexes if u.rstrip("/") != policy.required_index), None)
        if other is None:
            return None
        lines = (
            f"This repository installs only from its internal index, not {_host(other)}.",
            "Drop the index option; the configured index serves every package.",
        )
        return Finding(Decision.DENY, "required_index", lines)
    mixed = [u for kind, u in indexes if kind == "extra" or u.rstrip("/") not in DEFAULT_INDEXES]
    if not mixed:
        return None
    lines = (
        f"`{via}` adds the package index {_host(mixed[0])}, "
        "and mixing indexes is the dependency-confusion vector.",
        "Confirm the index with the user.",
    )
    return Finding(policy.index_mode, "index_mixing", lines)


def name_findings(names: Sequence[str], policy: DependencyPolicy, *, python: bool) -> list[Finding]:
    """Tier (b) and the overlay allowlist over requested names; declared Python names pass.

    Example::

        >>> name_findings(["requests"], policy_without_allowlist, python=True)[0].names
        ... # doctest: +SKIP
        ('requests',)
    """
    new = [name for name in names if not (python and name in policy.declared)]
    if not new:
        return []
    if policy.allowlist:
        outside = [name for name in new if name not in policy.allowlist]
        return [_not_allowed(outside, policy.allowlist)] if outside else []
    return [Finding(Decision.ASK, NEW_DEPENDENCY, names=tuple(new))]


def adding_line(names: Sequence[str]) -> str:
    """Tier (b)'s reason: ``Adding a, b. The playbook says ...``.

    Example::

        >>> adding_line(["rich"])
        "Adding rich. The playbook says don't add new dependencies without asking."
    """
    more = f" and {len(names) - _SHOWN_NAMES} more" if len(names) > _SHOWN_NAMES else ""
    shown = ", ".join(label(name) for name in names[:_SHOWN_NAMES])
    return f"Adding {shown}{more}. {NEW_DEPENDENCY_REASON}"


def label(name: str) -> str:
    """A requested name as shown to the model: control characters gone, 80 characters at most."""
    return clip(clean_text(name), 80)


def _not_allowed(names: Sequence[str], allowlist: Sequence[str]) -> Finding:
    import difflib  # branch-local (§D.1): only with an overlay allowlist

    hints = []
    for name in names[:_SHOWN_NAMES]:
        close = difflib.get_close_matches(name, allowlist, n=2, cutoff=0.75)
        hints.append(f"{label(name)} (did you mean {', '.join(close)}?)" if close else label(name))
    lines = (
        f"Not on this repository's dependency allowlist: {'; '.join(hints)}.",
        "Use an allowlisted package, or ask the user to extend the allowlist.",
    )
    return Finding(Decision.DENY, "not_allowlisted", lines)


def _host(url: str) -> str:
    return quote_data(url_host(url, bare=True) or url)


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]
