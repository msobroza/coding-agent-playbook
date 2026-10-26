"""Fixture editions for the pinned-sample tests (#281 ticket 09).

:func:`write_fixture_catalog` builds, under ``tmp_path``, a catalog with one core
prompt (``review``, including the rule ``typing``), that rule, and a core eval
sample ``review/pinned``. :func:`freeze_fixture_edition` then does what ticket
13's ``freeze`` will do: copies the prompt and the rule into
``editions/<tag>/core/`` (the frozen files carry the retired ``version`` and
``eval_samples`` keys, as old releases did), pins the sample and records the
digests. No git and no real tag is involved.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evals.sample_digest import rendered_prompt_digest, sample_digest
from coding_agent_playbook.evals.task_registry import load_task_sample
from coding_agent_playbook.release.edition import load_edition
from coding_agent_playbook.release.edition_digests import (
    DIGESTS_FILENAME,
    EditionArtifact,
    EditionDigests,
    PinDigests,
    edition_dir,
    render_edition_digests,
)

if TYPE_CHECKING:
    from pathlib import Path

TAG: Final = "v9.9.9"
ENGINE: Final = "coding_agent_playbook"
SAMPLE_ID: Final = "review/pinned"
PROMPT_PATH: Final = "core/prompts/review.md"
RULE_PATH: Final = "core/skills/python-coding/rules/typing.md"

FROZEN_PROMPT_BODY: Final = "Frozen review prompt.\n"
FROZEN_RULE_BODY: Final = "Frozen typing rule.\n"
CURRENT_PROMPT_BODY: Final = "Current review prompt.\n"
OVERRIDE_RULE_BODY: Final = "Local override of the typing rule.\n"

_PROMPT_TEXT: Final = (
    "---\nid: review\nname: Review\ndescription: Review code.\nslash: review\n"
    "{extra}includes_rules:\n  - typing\n---\n{body}"
)
_RULE_TEXT: Final = (
    "---\nid: typing\nname: Typing\ndescription: Type everything.\nscope: always\n"
    "{extra}---\n{body}"
)
_RETIRED_KEYS: Final = "version: 3\neval_samples:\n  - review/pinned\n"


def write_fixture_catalog(root: Path, *, edition: str | None = None) -> Path:
    """A catalog under ``root`` with the current ``review`` prompt and its sample; returns it.

    ``edition`` writes ``edition = "<tag>"`` into the sample's ``sample.toml``.
    """
    catalog = root / "catalog"
    prompt = catalog / PROMPT_PATH
    prompt.parent.mkdir(parents=True)
    prompt.write_text(_PROMPT_TEXT.format(extra="", body=CURRENT_PROMPT_BODY), encoding="utf-8")
    write_sample(catalog / "core", edition=edition)
    return catalog


def write_sample(layer: Path, *, edition: str | None, name: str = "pinned") -> Path:
    """``<layer>/eval_samples/review/<name>/sample.toml`` (plus a ``setup/``); returns its dir."""
    sample_dir = layer / "eval_samples" / "review" / name
    (sample_dir / "setup").mkdir(parents=True)
    (sample_dir / "setup" / "app.py").write_text("x = 1\n", encoding="utf-8")
    pin = f'edition = "{edition}"\n' if edition is not None else ""
    (sample_dir / "sample.toml").write_text(
        f'id = "review/{name}"\ndescription = "d"\n{pin}\n'
        '[gate.bind.ok]\ncheck = "file_exists"\npath = "app.py"\n\n[verdict]\ntrial = "gate"\n',
        encoding="utf-8",
    )
    return sample_dir


def write_local_rule_override(catalog: Path) -> Path:
    """A ``setup/playbook/rules/`` rule replacing ``typing``: a local-layer override."""
    rule = catalog / "core/eval_samples/review/pinned/setup/playbook/rules/typing.md"
    rule.parent.mkdir(parents=True)
    rule.write_text(_RULE_TEXT.format(extra="", body=OVERRIDE_RULE_BODY), encoding="utf-8")
    return rule


def write_edition_files(catalog: Path, tag: str = TAG) -> Path:
    """The frozen ``review`` prompt and ``typing`` rule under ``editions/<tag>/``; returns its dir."""
    root = edition_dir(catalog, tag)
    for rel, text in (
        (PROMPT_PATH, _PROMPT_TEXT.format(extra=_RETIRED_KEYS, body=FROZEN_PROMPT_BODY)),
        (RULE_PATH, _RULE_TEXT.format(extra="version: 2\n", body=FROZEN_RULE_BODY)),
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def write_digests(root: Path, tag: str = TAG, pins: tuple[PinDigests, ...] = ()) -> None:
    """``digests.toml`` listing the two frozen files of ``root`` with their byte digests."""
    artifacts = (
        EditionArtifact("prompt", "review", PROMPT_PATH, _sha256(root / PROMPT_PATH)),
        EditionArtifact("rule", "typing", RULE_PATH, _sha256(root / RULE_PATH)),
    )
    digests = EditionDigests(tag, "f00d", artifacts, pins)
    (root / DIGESTS_FILENAME).write_text(render_edition_digests(digests), encoding="utf-8")


def freeze_fixture_edition(catalog: Path, tag: str = TAG) -> Path:
    """Copy, pin and record ``review/pinned`` against edition ``tag``; returns the edition dir.

    The sample must already carry ``edition = "<tag>"``.
    """
    root = write_edition_files(catalog, tag)
    write_digests(root, tag)
    sample = load_task_sample(catalog / "core/eval_samples/review/pinned", source_package=ENGINE)
    rendered = rendered_prompt_digest(sample, load_edition(root))
    pin = PinDigests(SAMPLE_ID, rendered, sample_digest(sample))
    write_digests(root, tag, pins=(pin,))
    return root


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
