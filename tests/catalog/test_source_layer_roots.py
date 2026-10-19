"""``FileSystemArtifactSource.layer_roots`` and ``extra_resource_roots`` (prK §P P8).

One walk order feeds every artifact kind and validate's per-layer checks:
engine package, overlays, extra checkout ``resources/`` roots, repo-local
``playbook/``. Config-less ``playbook validate`` adds an overlay checkout's
``<root>/src/<pkg>/resources/`` as an extra root. Kept apart from
``tests/catalog/test_source.py`` for the file-size budget.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE
from coding_agent_playbook.catalog.source import FileSystemArtifactSource, _resource_subdir

if TYPE_CHECKING:
    from collections.abc import Callable

_RULE = "---\nid: {id}\nname: N\ndescription: d\nscope: always\n---\nBody\n"
_PROMPT = "---\nid: {id}\nname: N\ndescription: d\nslash: {id}\n---\nBody\n"
_SKILL = "---\nid: {id}\nname: {id}\ndescription: d\n---\nBody\n"
_TASK = 'id = "{id}"\nprompt_id = "{prompt}"\ndescription = "d"\n'


def _package_resources(name: str) -> Path:
    """The ``resources/`` dir of an importable package built by ``make_package``."""
    module = importlib.import_module(name)
    assert module.__file__ is not None
    return Path(module.__file__).parent / "resources"


def _checkout_root(repo: Path, package: str) -> Path:
    """``<repo>/src/<package>/resources`` with one artifact of every kind."""
    root = repo / "src" / package / "resources"
    for kind, name, text in (
        ("rules", "x-rule.md", _RULE.format(id="x-rule")),
        ("prompts", "x-prompt.md", _PROMPT.format(id="x-prompt")),
        ("skills", "x-skill/SKILL.md", _SKILL.format(id="x-skill")),
        ("eval_tasks", "x-task/task.toml", _TASK.format(id="x-task", prompt="x-prompt")),
    ):
        target = root / kind / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def test_layer_roots_orders_engine_overlays_checkout_repo_local(
    tmp_path: Path, make_package: Callable[..., str]
) -> None:
    overlay = make_package("layer_roots_overlay", resources=True)
    (_package_resources(overlay) / "rules").mkdir()
    checkout = _checkout_root(tmp_path, "acme_overlay")
    (tmp_path / "playbook" / "rules").mkdir(parents=True)
    source = FileSystemArtifactSource(
        repo_root=tmp_path, overlay_packages=[overlay], extra_resource_roots=[checkout]
    )

    layers = source.layer_roots("rules")

    assert layers == [
        (ENGINE_PACKAGE, _resource_subdir(ENGINE_PACKAGE, "rules")),
        (overlay, _resource_subdir(overlay, "rules")),
        ("acme_overlay", checkout / "rules"),
        ("<repo-local>", tmp_path / "playbook" / "rules"),
    ]


def test_layer_roots_skips_missing_subdirs(tmp_path: Path) -> None:
    checkout = tmp_path / "src" / "acme_overlay" / "resources"
    checkout.mkdir(parents=True)
    source = FileSystemArtifactSource(repo_root=tmp_path, extra_resource_roots=[checkout])

    assert source.layer_roots("rules") == [
        (ENGINE_PACKAGE, _resource_subdir(ENGINE_PACKAGE, "rules"))
    ]
    assert source.layer_roots("no-such-kind") == []


def test_extra_resource_roots_is_a_read_only_tuple(tmp_path: Path) -> None:
    checkout = tmp_path / "src" / "acme_overlay" / "resources"
    source = FileSystemArtifactSource(repo_root=tmp_path, extra_resource_roots=[checkout])
    assert source.extra_resource_roots == (checkout,)
    assert FileSystemArtifactSource(repo_root=tmp_path).extra_resource_roots == ()


def test_extra_resource_roots_feed_rules_prompts_skills_and_eval_tasks(tmp_path: Path) -> None:
    checkout = _checkout_root(tmp_path, "acme_overlay")
    source = FileSystemArtifactSource(repo_root=tmp_path, extra_resource_roots=[checkout])

    def from_checkout(ids_by_package: list[tuple[str, str]]) -> list[str]:
        return [item_id for item_id, package in ids_by_package if package == "acme_overlay"]

    rules = [(r.frontmatter.id, r.source_package) for r in source.list_rules()]
    prompts = [(p.frontmatter.id, p.source_package) for p in source.list_prompts()]
    skills = [(str(s.frontmatter.get("id")), s.source_package) for s in source.list_skills()]
    tasks = [(t.id, t.source_package) for t in source.list_eval_tasks()]
    assert from_checkout(rules) == ["x-rule"]
    assert from_checkout(prompts) == ["x-prompt"]
    assert from_checkout(skills) == ["x-skill"]
    assert from_checkout(tasks) == ["x-task"]
    # The engine layer still comes first: the checkout is an extra layer.
    assert rules[0][1] == ENGINE_PACKAGE
