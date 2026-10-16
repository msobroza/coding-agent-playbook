"""Docs-consistency guard for the PR-R6 ``Metric``/``Check``/``Rubric`` refactor.

These are prose-only assertions: they pin that the documentation reflects the
landed refactor and never silently reintroduces a deleted abstraction symbol as
the *current* model. They read no runtime code — only the repo's markdown — so
they cannot affect engine behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]

#: Symbols deleted by the R6 clean-slate refactor. They may still appear in
#: clearly-historical prose (changelogs, "was"/"former"/"superseded" notes), so
#: the body-presence guards below scope to the *current-model* doc, not a blanket
#: ban across every file.
_DELETED = ("evaluators_for_task", "value_kind", "ValueKind")


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def test_new_design_and_migration_docs_exist() -> None:
    assert (_ROOT / "specs" / "prR6-check-rubric.md").is_file()
    assert (_ROOT / "MIGRATION.md").is_file()


def test_prm_spec_carries_superseded_note() -> None:
    head = _read("specs/prM-code-metrics.md").splitlines()[:6]
    blob = "\n".join(head)
    assert "Superseded" in blob
    assert "prR6-check-rubric.md" in blob


def test_migration_covers_the_entry_point_rename_and_grade_swap() -> None:
    text = _read("MIGRATION.md")
    assert "coding_agent_playbook.metrics" in text
    assert "coding_agent_playbook.checks" in text
    assert "Rubric.evaluate" in text
    # The whole point: authors migrate nothing.
    assert "unchanged" in text.lower()


#: Cues that mark a *deleted* symbol as the old side of a port / a removal /
#: historical note rather than a live API element. A §21-body line naming a
#: deleted symbol is acceptable only when it also carries one of these.
_PORT_CUES = (
    "metric",
    "check",
    "rubric",
    "measure",
    "before",
    "old",
    "delete",
    "removed",
    "no ",  # "no value_kind/to_score" — documenting the absence
    "into",
    "fused",
    "refactor",
    "replaced",
    "supersed",
    "former",
    "originally",
    "→",
)


def test_migration_frames_the_evaluator_port() -> None:
    """``MIGRATION.md`` maps the old ``Evaluator`` API onto the new model.

    The guide necessarily names the deleted symbols (it is *about* porting them),
    so rather than ban the names this asserts the framing is present: the
    ``Evaluator`` → ``Metric`` rename and an explicit deleted-symbols list.
    """
    text = _read("MIGRATION.md")
    assert "Evaluator" in text and "Metric" in text
    # The deleted-symbols section names the retired API surface.
    for sym in ("Evaluator", "grade()", "evaluators_for_task", "ValueKind"):
        assert sym in text, f"MIGRATION.md missing the deleted symbol {sym!r}"


@pytest.mark.parametrize("symbol", _DELETED)
def test_spec_section_21_body_drops_deleted_symbols(symbol: str) -> None:
    """SPEC §21 (the *current* evaluator-subsystem section) must not present a
    deleted symbol as part of the live model.

    Scope to §21's body (up to the next ``## `` heading) — the trailing
    ``## Changelog`` appendix and the version changelog at the top legitimately
    mention the old names in past tense. A negative/historical mention (``no
    value_kind``, a removal list) is allowed; a bare reuse is not.
    """
    spec = _read("SPEC.md")
    start = spec.index("## 21. Code-quality evaluator subsystem")
    end = spec.index("\n## ", start + 1)
    body = spec[start:end]
    for line in body.splitlines():
        if symbol not in line:
            continue
        lowered = line.lower()
        assert any(cue in lowered for cue in _PORT_CUES), (
            f"SPEC §21 body presents deleted {symbol!r} as live: {line!r}"
        )


def test_spec_version_bumped_and_changelog_preserved() -> None:
    spec = _read("SPEC.md")
    # v0.18 (init and check --refresh never commit local overrides; unmanaged
    # entries preserved) is the current header, on top of v0.17 (bundled opt-in
    # packs), v0.16 (gitignored generated output) and v0.15 (native skills +
    # shared_skills); the guard cares that the refactor's changelog entries
    # survive later revisions.
    assert "| Version | 0.18 (draft) |" in spec
    assert "*End of SPEC.md v0.18.*" in spec
    assert "### v0.18" in spec  # the changelog appendix entry for the committed-config rewrite
    assert "### v0.17" in spec  # the changelog appendix entry for bundled opt-in packs
    assert "### v0.16" in spec  # the changelog appendix entry for gitignored output
    assert "### v0.15" in spec  # the changelog appendix entry for native skills
    assert "### v0.14" in spec  # the changelog appendix entry for self-contained links
    assert "### v0.13" in spec  # the changelog appendix entry for the task-config redesign
    assert "### v0.12" in spec  # the prior changelog appendix entry is preserved


def test_spec_section_21_documents_the_three_abstractions() -> None:
    spec = _read("SPEC.md")
    start = spec.index("## 21. Code-quality evaluator subsystem")
    end = spec.index("\n## ", start + 1)
    body = spec[start:end]
    for token in ("Metric", "Check", "Rubric", "scheduler", "CostTier"):
        assert token in body, f"SPEC §21 body missing {token!r}"
