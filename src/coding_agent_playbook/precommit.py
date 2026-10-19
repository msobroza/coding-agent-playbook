"""The pre-commit concept of ``playbook init``: the starter template and the text merge.

``playbook init`` renders the packaged air-gapped starter
(``templates/precommit/config.yaml.j2``) into a fresh repo (SPEC §13.2), and merges
the playbook hooks into an existing ``.pre-commit-config.yaml`` (SPEC §13.3).
``init`` computes the template switches from the committed config and passes them
as booleans, so this module reads no config and imports no command.

The merge never rewrites a config the consumer curates; it appends one
``- repo: local`` block for the ``[output] commit`` policy. Upgrading an older
consumer to the default ``commit = false`` needs one more step: the pre-v0.16
starter (and the block older ``init`` appended) carried the drift check
``coding-agent-playbook-sync`` = ``playbook sync --check``. Left in place it
reports drift after every checkout/merge — the output is no longer committed —
so when it is still byte-for-byte what ``init`` wrote it is swapped for the new
hooks in place; otherwise the user is told to delete it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from coding_agent_playbook.catalog.roots import ENGINE_PACKAGE
from coding_agent_playbook.renderer import build_environment, render_artifact_body

LEGACY_HOOK_ID = "coding-agent-playbook-sync"
GUARD_HOOK_ID = "coding-agent-playbook-no-generated-output"

_REPO_LOCAL = "  - repo: local\n    hooks:\n"
# Exactly what pre-v0.16 ``init`` wrote, both in the starter and when appending.
_LEGACY_HOOK = """\
      - id: coding-agent-playbook-sync
        name: coding-agent-playbook sync
        entry: playbook sync --check
        language: system
        pass_filenames: false
        always_run: true
"""
_LEGACY_STARTER_COMMENT = "      # The playbook — sync drift check\n"
# The verbatim hook, only when the next line is not another of its own (8-space)
# keys — a hook the user extended is not "what init wrote" and is left alone.
_LEGACY_PATTERNS = tuple(
    re.compile(re.escape(text) + r"(?! {8})")
    for text in (_LEGACY_STARTER_COMMENT + _LEGACY_HOOK, _LEGACY_HOOK)
)
# Default (commit = false): re-render the local-only output after checkout /
# merge, refuse commits that stage it. Stages are pinned on both.
_LOCAL_HOOKS = """\
      - id: coding-agent-playbook-autosync
        name: coding-agent-playbook sync (regenerate local output)
        entry: playbook sync
        language: system
        pass_filenames: false
        always_run: true
        stages: [post-checkout, post-merge]
      - id: coding-agent-playbook-no-generated-output
        name: coding-agent-playbook guard (no generated output staged)
        entry: playbook sync --check-staged
        language: system
        pass_filenames: false
        always_run: true
        stages: [pre-commit]
"""
_DEFAULT_STAGES = re.compile(r"^default_stages\s*:", re.MULTILINE)
_LEGACY_ID_LINE = re.compile(rf"\bid:\s*['\"]?{re.escape(LEGACY_HOOK_ID)}['\"]?\s*$", re.MULTILINE)

LEGACY_HOOK_WARNING = (
    f"warning: .pre-commit-config.yaml still declares the legacy '{LEGACY_HOOK_ID}' hook\n"
    "(playbook sync --check). With [output] commit = false the generated output is not\n"
    "committed, so it reports drift on every commit and after every checkout/merge —\n"
    "delete that hook."
)
DEFAULT_STAGES_NOTE = (
    "note: .pre-commit-config.yaml has no 'default_stages'. Hooks without 'stages:' run at\n"
    "every installed hook type, so once post-checkout/post-merge are installed your\n"
    "always_run hooks would also run after each checkout and pull. Add\n"
    "'default_stages: [pre-commit]' (or 'stages: [pre-commit]' per hook) first."
)


@dataclass(frozen=True)
class PreCommitMerge:
    """The merged config text plus messages for the user (never fatal)."""

    content: str
    messages: tuple[str, ...] = ()


def merge_pre_commit(content: str, *, output_commit: bool) -> PreCommitMerge:
    """Merge the playbook hooks for the ``[output] commit`` policy into ``content``.

    Example::

        >>> merged = merge_pre_commit("repos:\\n", output_commit=False)
        >>> "playbook sync --check-staged" in merged.content
        True
    """
    if output_commit:
        return PreCommitMerge(_append_once(content, LEGACY_HOOK_ID, _LEGACY_HOOK))
    merged = _append_once(_swap_legacy_hook(content), GUARD_HOOK_ID, _LOCAL_HOOKS)
    return PreCommitMerge(merged, _local_messages(merged))


def _swap_legacy_hook(content: str) -> str:
    """Replace the verbatim init-written legacy hook with the ``commit = false`` pair.

    Only when the new guard is absent (replacing keeps the ``hooks:`` list
    non-empty); a hand-edited legacy hook is left for :func:`_local_messages`.
    """
    if GUARD_HOOK_ID in content:
        return content
    for legacy in _LEGACY_PATTERNS:
        swapped, count = legacy.subn(lambda _match: _LOCAL_HOOKS, content, count=1)
        if count:
            return swapped
    return content


def _append_once(content: str, hook_id: str, hooks: str) -> str:
    """Append a ``- repo: local`` block with ``hooks`` unless ``hook_id`` is declared."""
    if hook_id in content:
        return content
    if not content.endswith("\n"):
        content += "\n"
    return content + _REPO_LOCAL + hooks


def _local_messages(merged: str) -> tuple[str, ...]:
    """Warnings for a ``commit = false`` config the merge could not fix itself."""
    messages: list[str] = []
    if _LEGACY_ID_LINE.search(merged):
        messages.append(LEGACY_HOOK_WARNING)
    if not _DEFAULT_STAGES.search(merged):
        messages.append(DEFAULT_STAGES_NOTE)
    return tuple(messages)


_PRECOMMIT_TEMPLATE_NAME = "config.yaml.j2"


class PrecommitTemplateMissingError(RuntimeError):
    """The engine's packaged pre-commit template is not where the install put it.

    ``path`` is the template file that was expected. An explicit error, not an
    ``assert``: ``python -O`` strips asserts, which would turn a broken install
    into a confusing failure deep inside the renderer.
    """

    def __init__(self, path: Path) -> None:
        super().__init__(
            f"the engine's pre-commit template was not found at {path}; "
            "reinstall coding-agent-playbook"
        )
        self.path = path


def precommit_template_dir(templates_root: Path | None = None) -> Path:
    """Return the directory holding the engine's pre-commit template.

    The template is engine wiring, not playbook content (its hook ids are
    duplicated in :func:`merge_pre_commit`), so it lives in the package's
    ``templates/precommit/`` rather than the catalog. ``templates_root``
    defaults to the engine's ``templates/``; tests pass another root. Raises
    :class:`PrecommitTemplateMissingError` when the directory or
    ``config.yaml.j2`` is missing.

    Example::

        >>> (precommit_template_dir() / "config.yaml.j2").is_file()
        True
    """
    if templates_root is None:
        templates_root = Path(str(resources.files(ENGINE_PACKAGE) / "templates"))
    template_dir = templates_root / "precommit"
    if not (template_dir / _PRECOMMIT_TEMPLATE_NAME).is_file():
        raise PrecommitTemplateMissingError(template_dir / _PRECOMMIT_TEMPLATE_NAME)
    return template_dir


def render_fresh_pre_commit(
    *, output_commit: bool = False, commit_trailers: bool = False, commitizen: bool = False
) -> str:
    """Render the packaged starter ``.pre-commit-config.yaml`` template.

    The template (``templates/precommit/config.yaml.j2``) is air-gapped: every
    hook is ``repo: local`` + ``language: system`` so pre-commit never clones a
    remote hook repo. ``output_commit`` (the ``[output] commit`` policy) selects
    the playbook hooks: the legacy drift check for ``true``; the post-checkout /
    post-merge auto-sync plus the staged-output guard for ``false``.
    ``commit_trailers`` (a trailer row is configured, prK §E.4) adds the
    ``coding-agent-playbook-commit-trailers`` commit-msg entry and installs that
    stage; ``commitizen`` (the repo opted into a commitizen convention, prK §F.4.3)
    adds ``coding-agent-playbook-commit-msg`` (``cz check``) the same way, so a
    consumer without commitizen never gets a commit hook that cannot run. We
    still stash an empty facts dict to honour the renderer's helper contract
    (SPEC §9.4).

    Example::

        >>> "--check-staged" in render_fresh_pre_commit()
        True
    """
    precommit_dir = precommit_template_dir()
    template_path = precommit_dir / _PRECOMMIT_TEMPLATE_NAME
    env = build_environment([precommit_dir])
    env.globals["_facts"] = {}
    variables = {
        "output_commit": output_commit,
        "commit_trailers": commit_trailers,
        "commitizen": commitizen,
    }
    return render_artifact_body(template_path, variables, env=env)


def write_pre_commit(
    repo_root: Path,
    *,
    output_commit: bool = False,
    commit_trailers: bool = False,
    commitizen: bool = False,
) -> tuple[Path, tuple[str, ...]]:
    """Write or merge ``.pre-commit-config.yaml``; return it plus user messages.

    Fresh repo: render the full air-gapped starter (playbook + ruff + mypy
    hooks). Existing config: merge only our playbook hooks for the
    ``[output] commit`` policy (:func:`merge_pre_commit`: append once, swapping a
    verbatim pre-v0.16 drift-check hook for the ``commit = false`` pair) — we
    never inject ruff/mypy into a config the consumer already curates
    (SPEC §13.3). The merge is intentionally text-based. ``commit_trailers`` and
    ``commitizen`` are the starter's switches (:func:`render_fresh_pre_commit`);
    ``init`` computes them from the committed config, so this module reads none.

    Example::

        >>> path, messages = write_pre_commit(repo_root, output_commit=False)
        >>> path.name
        '.pre-commit-config.yaml'
    """
    target = repo_root / ".pre-commit-config.yaml"
    if not target.is_file():
        starter = render_fresh_pre_commit(
            output_commit=output_commit,
            commit_trailers=commit_trailers,
            commitizen=commitizen,
        )
        target.write_text(starter, encoding="utf-8")
        return target, ()
    content = target.read_text(encoding="utf-8")
    merged = merge_pre_commit(content, output_commit=output_commit)
    if merged.content != content:
        target.write_text(merged.content, encoding="utf-8")
    return target, merged.messages
