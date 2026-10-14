"""Merge the playbook hooks into an existing ``.pre-commit-config.yaml`` (SPEC §13.3).

``playbook init`` never rewrites a config the consumer curates; it appends one
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
