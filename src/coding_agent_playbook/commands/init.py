"""`playbook init` — interactive (or flag-driven) bootstrap for a fresh repo
(SPEC §12.1)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

from coding_agent_playbook import __version__ as _engine_version
from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.commands._precommit_merge import merge_pre_commit
from coding_agent_playbook.config import Config, OutputConfig, ProjectMeta, StorageConfig
from coding_agent_playbook.detector import detect
from coding_agent_playbook.renderer import build_environment, render_artifact_body
from coding_agent_playbook.sources.filesystem import FileSystemStateSource, _resource_subdir

if TYPE_CHECKING:
    import argparse

    from coding_agent_playbook.detector import Facts


class _Answers(TypedDict):
    """Shape of the user-collected answers handed to ``_write_config``.

    Keeping this in a TypedDict lets mypy verify each field is the right
    type without sprinkling ``cast`` / ``type: ignore`` at every key access.
    """

    name: str
    kind: str
    description: str
    adapters: list[str]
    overlays: list[str]


# ``shared_skills`` (the cross-agent skills hub, SPEC §10.8) is on by default but,
# unlike ``agents_md``, not force-enabled: users may drop it from [adapters] enabled.
_DEFAULT_ADAPTERS = ("continue", "claude_code", "opencode", "shared_skills")
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
        adapters_raw = getattr(args, "adapters", None) or ",".join(_DEFAULT_ADAPTERS)
        adapters = [a.strip() for a in str(adapters_raw).split(",") if a.strip()]
        overlays_raw = getattr(args, "overlays", "") or ""
        overlays = [o.strip() for o in str(overlays_raw).split(",") if o.strip()]
        return _Answers(
            name=str(name),
            kind=str(kind),
            description=str(getattr(args, "description", "") or ""),
            adapters=adapters,
            overlays=overlays,
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
        "Which assistants will the team use?",
        [*_DEFAULT_ADAPTERS, "codex"],
        list(_DEFAULT_ADAPTERS),
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
    )


def _write_config(repo_root: Path, answers: _Answers) -> Config:
    """Write or update ``.coding-agent-playbook.toml`` with the user's
    answers and return the written :class:`Config`. Idempotent: an existing
    config is *merged* with the new answers — user-edited fields win over
    freshly-asked defaults, but new defaults (e.g. for a freshly-added
    adapter) are added in.

    ``[output] commit`` is always written explicitly (``false`` unless the
    user already chose otherwise) so the output policy is discoverable.
    """
    primary = repo_root / FileSystemStateSource._CONFIG_FILENAME

    facts = detect(repo_root)
    detector_cache = _facts_to_cache(facts)

    if primary.is_file():
        # Existing config: load it through the state source, then surgically
        # update the fields we know about. Anything the user added that we
        # don't know about is preserved.
        state = FileSystemStateSource(repo_root=repo_root)
        existing = state.load_config()
        existing.project = ProjectMeta(
            name=answers["name"],
            kind=answers["kind"],
            description=answers["description"],
        )
        # Adapters: union of existing and new defaults, preserving order.
        existing_adapters = list(existing.adapters_enabled)
        for adapter in answers["adapters"]:
            if adapter not in existing_adapters:
                existing_adapters.append(adapter)
        existing.adapters_enabled = existing_adapters
        existing.overlays_enabled = list(answers["overlays"])
        existing.detector_cache = detector_cache
        if existing.output is None:
            existing.output = OutputConfig(commit=False)
        config = existing
    else:
        config = Config(
            schema_version=1,
            project=ProjectMeta(
                name=answers["name"],
                kind=answers["kind"],
                description=answers["description"],
            ),
            engine_version=_engine_version,
            overlays_enabled=list(answers["overlays"]),
            adapters_enabled=list(answers["adapters"]),
            storage=StorageConfig(),
            detector_cache=detector_cache,
            output=OutputConfig(commit=False),
        )

    state = FileSystemStateSource(repo_root=repo_root)
    state.save_config(config)
    return config


def _facts_to_cache(facts: Facts) -> dict[str, object]:
    """Project ``Facts`` into a TOML-serializable shape for the
    ``detector_cache`` table.

    ``Facts`` is a ``TypedDict`` with ``total=False``; we treat it as an
    open mapping at this seam since we only inspect values, not keys.

    Sets are not TOML; lists are. Booleans/strings/ints pass through.
    """
    cache: dict[str, object] = {}
    for key, value in facts.items():
        if isinstance(value, set):
            cache[key] = sorted(value)
        else:
            cache[key] = value
    return cache


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


def _render_fresh_pre_commit(*, output_commit: bool = False) -> str:
    """Render the packaged starter ``.pre-commit-config.yaml`` template.

    The template (``resources/precommit/config.yaml.j2``) is air-gapped: every
    hook is ``repo: local`` + ``language: system`` so pre-commit never clones a
    remote hook repo. ``output_commit`` (the ``[output] commit`` policy) selects
    the playbook hooks: the legacy drift check for ``true``; the post-checkout /
    post-merge auto-sync plus the staged-output guard for ``false``. We still
    stash an empty facts dict to honour the renderer's helper contract (SPEC §9.4).

    Example::

        >>> "--check-staged" in _render_fresh_pre_commit()
        True
    """
    precommit_dir = _resource_subdir("coding_agent_playbook", "precommit")
    assert precommit_dir is not None, "packaged resources/precommit/ is missing"
    template_path = precommit_dir / "config.yaml.j2"
    env = build_environment([precommit_dir])
    env.globals["_facts"] = {}
    return render_artifact_body(template_path, {"output_commit": output_commit}, env=env)


def _write_pre_commit(
    repo_root: Path, *, output_commit: bool = False
) -> tuple[Path, tuple[str, ...]]:
    """Write or merge ``.pre-commit-config.yaml``; return it plus user messages.

    Fresh repo: render the full air-gapped starter (playbook + ruff + mypy
    hooks). Existing config: merge only our playbook hooks for the
    ``[output] commit`` policy (``_precommit_merge``: append once, swapping a
    verbatim pre-v0.16 drift-check hook for the ``commit = false`` pair) — we
    never inject ruff/mypy into a config the consumer already curates
    (SPEC §13.3). The merge is intentionally text-based.
    """
    target = repo_root / ".pre-commit-config.yaml"
    if not target.is_file():
        target.write_text(_render_fresh_pre_commit(output_commit=output_commit), encoding="utf-8")
        return target, ()
    content = target.read_text(encoding="utf-8")
    merged = merge_pre_commit(content, output_commit=output_commit)
    if merged.content != content:
        target.write_text(merged.content, encoding="utf-8")
    return target, merged.messages


def run(args: argparse.Namespace) -> int:
    repo_root = Path(getattr(args, "repo_root", None) or Path.cwd())
    answers = _collect_answers(args)

    config = _write_config(repo_root, answers)
    local_path = _write_local_config(repo_root)
    gitignore_path = _append_to_gitignore(repo_root)
    pre_commit_path, pre_commit_messages = _write_pre_commit(
        repo_root, output_commit=config.commit_output
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
