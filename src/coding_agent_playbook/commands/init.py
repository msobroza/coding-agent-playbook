"""`playbook init` — interactive (or flag-driven) bootstrap for a fresh repo
(SPEC §12.1).

It also asks whether to enable assistant lifecycle hooks and writes the answer
as ``[hooks] enabled`` (specs/prK-lifecycle-hooks.md §B.1, OQ-3): an absent
table means off, so an engine upgrade never switches executable hooks on.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

from coding_agent_playbook import __version__ as _engine_version
from coding_agent_playbook.catalog.roots import (
    canonical_overlay_list,
    canonical_overlay_name,
    catalog_root,
)
from coding_agent_playbook.commands import _sync_preflight
from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.commands._init_adapters import (
    ADAPTER_CHOICES,
    ADAPTERS_QUESTION,
    DEFAULT_ADAPTERS,
    adapters_from_flag,
    adapters_union,
)
from coding_agent_playbook.config.committed import (
    ConfigRewrite,
    detector_cache_table,
    plan_committed_update,
    plan_first_config,
)
from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.config.model import Config, OutputConfig, ProjectMeta, StorageConfig
from coding_agent_playbook.detector.facts import detect
from coding_agent_playbook.precommit import write_pre_commit

if TYPE_CHECKING:
    import argparse
    from collections.abc import Mapping


class _Answers(TypedDict):
    """Shape of the user-collected answers handed to ``_plan_config``.

    Keeping this in a TypedDict lets mypy verify each field is the right
    type without sprinkling ``cast`` / ``type: ignore`` at every key access.
    """

    name: str
    kind: str
    description: str
    adapters: list[str]
    overlays: list[str]
    # ``[hooks] enabled``; None = no explicit choice (non-interactive without
    # --no-hooks): keep a value the config already has, else enable.
    hooks: bool | None


_VALID_KINDS = (
    "python-application",
    "python-library",
    "ml-research",
    "notebook",
    "python-unknown",
)

#: The three git hook types a ``commit = false`` repo needs installed.
_HOOK_INSTALL_COMMAND = (
    "pre-commit install --hook-type pre-commit --hook-type post-checkout --hook-type post-merge"
)

_GITIGNORE_LINE = ".coding-agent-playbook.local.toml"

_HOOKS_QUESTION = "Enable assistant lifecycle hooks?"
_YES = frozenset({"y", "yes"})
_NO = frozenset({"n", "no"})


def _prompt(question: str, default: str | None = None) -> str:
    """Wrap ``input()`` with an optional default. Returns the user's reply
    (stripped) or ``default`` when the reply is empty."""
    suffix = f" [{default}]" if default else ""
    answer = input(f"{question}{suffix}: ").strip()
    return answer or (default or "")


def _prompt_multi_select(question: str, choices: list[str], defaults: list[str]) -> list[str]:
    """Ask a multi-select question. The user enters comma-separated indices
    (1-based); an empty reply accepts ``defaults``."""
    print(f"{question} (comma-separated indices, blank=defaults={', '.join(defaults)})")
    for index, choice in enumerate(choices, start=1):
        marker = "*" if choice in defaults else " "
        print(f"  {marker} {index}. {choice}")
    answer = input("> ").strip()
    if not answer:
        return list(defaults)
    selected: list[str] = []
    for token in answer.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            idx = int(token)
        except ValueError:
            continue
        if 1 <= idx <= len(choices):
            selected.append(choices[idx - 1])
    return selected or list(defaults)


def _prompt_yes_no(question: str, *, default: bool = True) -> bool:
    """Ask a yes/no question until the reply is clear; an empty reply takes ``default``.

    Example: ``_prompt_yes_no("Enable assistant lifecycle hooks?")`` asks ``... [Y/n]: ``.
    """
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        answer = input(f"{question} {suffix}: ").strip().lower()
        if not answer:
            return default
        if answer in _YES or answer in _NO:
            return answer in _YES


def _hooks_answer(args: argparse.Namespace, *, interactive: bool) -> bool | None:
    """``False`` for ``--no-hooks``; the user's answer when interactive; else no choice (None)."""
    if getattr(args, "no_hooks", False):
        return False
    return _prompt_yes_no(_HOOKS_QUESTION) if interactive else None


def _collect_answers(args: argparse.Namespace) -> _Answers:
    """Resolve the project parameters from flags (non-interactive) or prompts
    (interactive). Returns a typed mapping the writer functions consume."""
    if getattr(args, "non_interactive", False):
        name = getattr(args, "name", None)
        kind = getattr(args, "kind", None)
        if not name or not kind:
            print(
                "error: --name and --kind are required in non-interactive mode",
                file=sys.stderr,
            )
            raise SystemExit(2)
        if kind not in _VALID_KINDS:
            print(
                f"error: --kind must be one of: {', '.join(_VALID_KINDS)}",
                file=sys.stderr,
            )
            raise SystemExit(2)
        adapters = adapters_from_flag(getattr(args, "adapters", None))
        overlays_raw = getattr(args, "overlays", "") or ""
        overlays = [o.strip() for o in str(overlays_raw).split(",") if o.strip()]
        return _Answers(
            name=str(name),
            kind=str(kind),
            description=str(getattr(args, "description", "") or ""),
            adapters=adapters,
            overlays=overlays,
            hooks=_hooks_answer(args, interactive=False),
        )
    # Interactive path.
    name = _prompt("Project name")
    while not name:
        name = _prompt("Project name (required)")
    description = _prompt("Project description", default="")
    kind = _prompt("Project kind", default="python-application")
    while kind not in _VALID_KINDS:
        print(f"  valid kinds: {', '.join(_VALID_KINDS)}")
        kind = _prompt("Project kind", default="python-application")
    adapters = _prompt_multi_select(
        ADAPTERS_QUESTION, list(ADAPTER_CHOICES), list(DEFAULT_ADAPTERS)
    )
    overlays = _prompt_multi_select(
        "Enable overlay packages?",
        [],
        [],
    )
    return _Answers(
        name=name,
        kind=kind,
        description=description,
        adapters=adapters,
        overlays=overlays,
        hooks=_hooks_answer(args, interactive=True),
    )


def _plan_config(state: FileSystemStateSource, repo_root: Path, answers: _Answers) -> ConfigRewrite:
    """What ``init`` will write to ``.coding-agent-playbook.toml``, checked; nothing written.

    An existing file is rewritten from **itself alone**: never from
    ``load_config``, whose merge with the gitignored
    ``.coding-agent-playbook.local.toml`` (SPEC §7.2) would commit one engineer's
    personal overrides — adapters, overlays, ``[user_choices]``, ``[output]`` —
    for the whole team. On a re-run:

    * the keys ``Config`` owns are replaced, not merged, by the updated committed
      ``Config`` (:func:`_apply_answers`), so an emptied or omitted ``--overlays``
      (both mean no overlays), a dropped description or a stale
      ``[detector_cache]`` entry stays dropped. Owned: every top-level key in
      ``config.entries.CONFIG_MANAGED_KEYS``, ``[detector_cache]`` and ``[user_choices]``
      whole, and the keys ``Config`` reads inside ``[project]``/``[engine]``/
      ``[storage]``/``[output]`` (``config.entries.CONFIG_MANAGED_TABLE_KEYS``);
    * everything else is written back as parsed (it rides along in
      ``Config.extra_tables``, P6): other top-level keys (``[hooks]``,
      ``[guardrails]``, ``[links]``, ``[metrics]``, future tables, which their
      commands read from the raw TOML) and unknown keys inside those four tables
      (``[project] homepage``) — except ``[hooks] enabled``, which takes the hooks
      answer (:func:`_with_hooks_answer`).

    Values survive; comments and layout do not (the file is re-serialized).
    ``[output] commit`` is always written explicitly (``false`` unless the file
    already chose otherwise) so the output policy is discoverable.

    Raises ``ConfigError`` (exit 2) for a committed file ``Config`` would misread
    — including one missing a required key (``[engine] version``…) that only the
    local file supplies: init neither copies that personal value into the
    committed file nor guesses a team-wide one. Last, the planned config with
    the local file merged on top must load (``FileSystemStateSource.preview_config``):
    only init's final sync would otherwise load it, after the committed files
    were rewritten. Both paths are ``config.committed``'s, which ``check
    --refresh`` shares.
    """
    detector_cache = detector_cache_table(detect(repo_root))
    hooks = answers["hooks"]
    if not state.has_committed_config():
        fresh = _fresh_config(answers, detector_cache)
        return plan_first_config(state, _with_hooks_answer(fresh, hooks))
    return plan_committed_update(
        state,
        lambda committed: _with_hooks_answer(
            _apply_answers(committed, answers, detector_cache), hooks
        ),
    )


def _project_meta(answers: _Answers) -> ProjectMeta:
    """The ``[project]`` table init writes, straight from the answers."""
    return ProjectMeta(
        name=answers["name"], kind=answers["kind"], description=answers["description"]
    )


def _with_hooks_answer(config: Config, answer: bool | None) -> Config:
    """``config`` with ``[hooks] enabled`` set through ``extra_tables`` (P6), other keys kept.

    No explicit ``answer`` keeps an ``enabled`` the committed table already
    has (a re-run never flips an earlier choice), else enables hooks.

    Example::

        _with_hooks_answer(config, False).extra_tables["hooks"]["enabled"]  # False
    """
    existing = config.extra_tables.get("hooks")
    table = dict(existing) if isinstance(existing, dict) else {}
    if answer is None and "enabled" in table:
        return config
    table["enabled"] = True if answer is None else answer
    return dataclasses.replace(config, extra_tables={**config.extra_tables, "hooks": table})


def _fresh_config(answers: _Answers, detector_cache: dict[str, object]) -> Config:
    """The config for a repo with no committed file yet (``[output] commit = false``)."""
    return Config(
        schema_version=1,
        project=_project_meta(answers),
        engine_version=_engine_version,
        overlays_enabled=list(answers["overlays"]),
        adapters_enabled=list(answers["adapters"]),
        storage=StorageConfig(),
        detector_cache=detector_cache,
        output=OutputConfig(commit=False),
    )


def _apply_answers(
    committed: Config, answers: _Answers, detector_cache: dict[str, object]
) -> Config:
    """``committed`` updated by a re-run: what each managed field becomes.

    ``[project]`` and ``overlays_enabled`` come from the answers, the adapters are
    :func:`~coding_agent_playbook.commands._init_adapters.adapters_union`,
    ``[detector_cache]`` is fresh, ``[output]`` is kept
    (else ``commit = false``); ``[engine]``, ``[storage]`` and the committed
    ``[user_choices]`` are kept as they are.

    Example::

        >>> _apply_answers(committed, answers, {}).overlays_enabled  # doctest: +SKIP
        []
    """
    return dataclasses.replace(
        committed,
        project=_project_meta(answers),
        adapters_enabled=adapters_union(committed.adapters_enabled, answers["adapters"]),
        overlays_enabled=list(answers["overlays"]),
        detector_cache=detector_cache,
        output=committed.output if committed.output is not None else OutputConfig(commit=False),
    )


def _write_local_config(repo_root: Path) -> Path:
    """Create an empty ``.coding-agent-playbook.local.toml`` if missing.

    The file is gitignored so personal/local overrides don't pollute the
    repo. The empty file is enough for the load path to find it.
    """
    target = repo_root / FileSystemStateSource._CONFIG_LOCAL_FILENAME
    if not target.is_file():
        target.write_text("[user_choices]\n", encoding="utf-8")
    return target


def _append_to_gitignore(repo_root: Path) -> Path:
    gitignore = repo_root / ".gitignore"
    if gitignore.is_file():
        content = gitignore.read_text(encoding="utf-8")
        if _GITIGNORE_LINE in content:
            return gitignore
        if content and not content.endswith("\n"):
            content += "\n"
        content += f"{_GITIGNORE_LINE}\n"
    else:
        content = f"{_GITIGNORE_LINE}\n"
    gitignore.write_text(content, encoding="utf-8")
    return gitignore


def _has_trailer_rows(repo_root: Path) -> bool:
    """Whether the committed config sets a commit-trailer row (prK §E.4); ``False`` if unreadable.

    The final sync reports a config it cannot read; the starter simply leaves the
    commit-msg entry out (an existing ``.pre-commit-config.yaml`` is never touched).
    """
    from coding_agent_playbook.commands._twin_policy import commit_trailer_policy

    try:
        return commit_trailer_policy(repo_root).has_rows
    except (ValueError, OSError, KeyError, TypeError):
        return False


def _uses_commitizen(repo_root: Path) -> bool:
    """Whether the repo opted into a commitizen convention (``playbook ci``'s predicate, §F.5).

    An unreadable ``pyproject.toml`` or config counts as opted in, as for CI.
    """
    from coding_agent_playbook.commands._ci_policy import commit_convention_configured

    return commit_convention_configured(repo_root)


def _overlay_lists_to_check(
    answers: _Answers, local: Mapping[str, Any]
) -> list[tuple[list[str], str]]:
    """Each overlay list init must check before writing, with the setting that lists it.

    ``--overlays`` always: it is what the committed file gets, so every teammate
    without a local file syncs with it. And a local ``overlays_enabled`` when
    ``.coding-agent-playbook.local.toml`` sets one: it replaces the committed
    list (SPEC §7.2), so it is what init's own final sync runs with. Checking
    only that one let an unusable ``--overlays`` reach the committed file, where
    it broke every teammate's ``playbook sync``.

    Example::

        >>> _overlay_lists_to_check({"overlays": ["a"]}, {"overlays_enabled": ["b"]})  # doctest: +SKIP
        [(['a'], '--overlays'), (['b'], 'overlays_enabled in .coding-agent-playbook.local.toml')]
    """
    lists = [(list(answers["overlays"]), "--overlays")]
    if "overlays_enabled" in local:
        origin = f"overlays_enabled in {FileSystemStateSource._CONFIG_LOCAL_FILENAME}"
        lists.append((list(local["overlays_enabled"]), origin))
    return lists


def _refuse_unusable_overlays(overlays: list[str], origin: str) -> bool:
    """Print an ``error:`` and return ``True`` when one of ``overlays`` is unusable.

    Uses the sync preflight's own check, so init never writes a config that
    every ``playbook sync`` mode would then refuse to run with. ``origin`` names
    the setting the overlays came from (``--overlays`` or the local file's list).
    """
    unusable = _sync_preflight.unusable_overlays(overlays)
    if not unusable:
        return False
    listed = "".join(f"\n  {problem}" for problem in unusable)
    print(
        f"error: {origin} names overlay package(s) or bundled plugin(s) that cannot be used "
        f"here; nothing was written:{listed}",
        file=sys.stderr,
    )
    return True


def _warn_deprecated_flag_overlays(deprecated: tuple[str, ...]) -> None:
    """Print one stderr ``warning: --overlays:`` line per distinct deprecated name.

    ``deprecated`` is what ``canonical_overlay_list`` rewrote in ``--overlays``
    (SPEC v0.19). The local file's list is not warned about here: init's final
    sync goes through ``SyncContext.from_repo``, which does that.

    Example::

        >>> _warn_deprecated_flag_overlays(deprecated)  # doctest: +SKIP
        warning: --overlays: '<old>' is deprecated; use '<new>'
    """
    for old in dict.fromkeys(deprecated):
        print(
            f"warning: --overlays: '{old}' is deprecated; use '{canonical_overlay_name(old)}'",
            file=sys.stderr,
        )


def run(args: argparse.Namespace) -> int:
    """Bootstrap the repo: write the config files and pre-commit hooks, then sync.

    Exit 2, before writing anything, on a usage error: missing flags, an unusable
    overlay in ``--overlays`` (what the committed file gets) or in the local
    file's ``overlays_enabled`` (what the final sync uses), or (raised as
    ``ConfigError``) a config file the engine would misread. Both files are read
    and checked here — the local one on its own, the committed one on its own,
    then the config the final sync will load (:func:`_plan_config`) — so a broken
    file of either kind leaves the repo untouched. A broken install exits 2
    before writing too: :func:`catalog_root` raises
    ``CatalogMissingError`` when the engine's catalog is missing,
    and ``cli.main`` reports it. A deprecated
    ``coding_agent_playbook.packs.*`` name in ``--overlays`` is written in its
    canonical ``plugins`` spelling (on a re-run too: the migration path for the
    committed file) and warned about once the overlay preflight passes.
    """
    repo_root = Path(getattr(args, "repo_root", None) or Path.cwd())
    answers = _collect_answers(args)
    answers["overlays"], deprecated_flags = canonical_overlay_list(answers["overlays"])
    state = FileSystemStateSource(repo_root=repo_root)
    local = state.load_local_overrides()
    catalog_root()  # a broken install raises here: never a half-initialized repo
    refused = [
        _refuse_unusable_overlays(overlays, origin)
        for overlays, origin in _overlay_lists_to_check(answers, local)
    ]
    if any(refused):
        return 2
    _warn_deprecated_flag_overlays(deprecated_flags)
    plan = _plan_config(state, repo_root, answers)

    # Nothing is written above this line.
    config = plan.save(state)
    local_path = _write_local_config(repo_root)
    gitignore_path = _append_to_gitignore(repo_root)
    # The starter switches matter only for a fresh config (a merge ignores them),
    # so the predicates parse config/pyproject only then, as before the N9 move.
    fresh_pre_commit = not (repo_root / ".pre-commit-config.yaml").is_file()
    pre_commit_path, pre_commit_messages = write_pre_commit(
        repo_root,
        output_commit=config.commit_output,
        commit_trailers=fresh_pre_commit and _has_trailer_rows(repo_root),
        commitizen=fresh_pre_commit and _uses_commitizen(repo_root),
    )

    print(f"Wrote {FileSystemStateSource._CONFIG_FILENAME}")
    print(f"Wrote {local_path.name}")
    print(f"Updated {gitignore_path.name}")
    print(f"Updated {pre_commit_path.name}")
    for message in pre_commit_messages:
        print(message, file=sys.stderr)
    if not config.commit_output:
        # Generated output is gitignored ([output] commit = false): the
        # post-checkout/post-merge hooks are what re-render it for teammates.
        print(f"Install the git hooks with: {_HOOK_INSTALL_COMMAND}")

    # Final step: invoke ``playbook sync`` so the consumer's first call lands real
    # output. Use the typed programmatic entry point (``sync.execute``) so
    # we don't have to fake an argparse.Namespace.
    return _sync.execute(repo_root=repo_root, check=False)
