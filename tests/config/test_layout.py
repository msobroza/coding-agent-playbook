"""The ``[layout]`` table of the committed config and the prefix rewriter (D60, D71; prU L0-23)."""

from __future__ import annotations

from typing import Any

import pytest

from coding_agent_playbook.config.layout import (
    LAYOUT_DEFAULTS,
    LAYOUT_KEYS,
    LayoutRewriter,
    RewriteCount,
    resolve_layout,
)
from coding_agent_playbook.config.model import Config
from coding_agent_playbook.config.schema import ConfigError, check_layout_table

_BASE: dict[str, Any] = {
    "schema_version": 1,
    "project": {"name": "x", "kind": "python-library"},
    "engine": {"version": "0.1.0"},
}


def test_defaults_are_the_d60_layout() -> None:
    assert dict(LAYOUT_DEFAULTS) == {
        "glossary": "CONTEXT.md",
        "context_map": "CONTEXT-MAP.md",
        "adr": "docs/adr",
        "architecture": "docs/architecture.md",
        "specs": "docs/specs",
        "plans": "docs/plans",
        "research": "docs/research",
        "agents": "docs/agents",
        "scratch": ".scratch",
    }


def test_resolve_layout_keeps_defaults_for_keys_left_out() -> None:
    resolved = resolve_layout({"specs": "specs"})

    assert resolved["specs"] == "specs"
    assert resolved["plans"] == "docs/plans"


def test_config_reads_and_writes_the_layout_table() -> None:
    config = Config.from_dict({**_BASE, "layout": {"specs": "specs"}})

    assert config.layout == {"specs": "specs"}
    assert config.to_dict()["layout"] == {"specs": "specs"}
    assert "layout" not in Config.from_dict(dict(_BASE)).to_dict()


@pytest.mark.parametrize(
    ("table", "fragment"),
    [
        ({"specs": "/abs/specs"}, "[layout] specs must be a relative path inside the repo"),
        ({"plans": "docs/../plans"}, "[layout] plans must not contain a '..' segment"),
        ({"adr": "docs/adr/"}, "[layout] adr must not end with '/'"),
        ({"adr": ""}, "[layout] adr must be a non-empty string"),
        ({"adr": 3}, "[layout] adr must be a non-empty string"),
        ({"spec": "specs"}, "[layout] unknown key 'spec'"),
        ({"research": "C:\\notes"}, "[layout] research must be a relative path inside the repo"),
        ({"agents": "./agents"}, "[layout] agents must not contain a '.' or empty segment"),
    ],
)
def test_check_layout_table_names_the_key(table: dict[str, object], fragment: str) -> None:
    with pytest.raises(ConfigError, match=r"^c\.toml: ") as caught:
        check_layout_table({"layout": table}, source="c.toml")

    assert fragment in str(caught.value)


def test_a_layout_that_is_not_a_table_is_refused() -> None:
    with pytest.raises(ConfigError, match=r"\[layout\] must be a table"):
        Config.from_dict({**_BASE, "layout": "specs"}, source="c.toml")


def test_an_unknown_layout_key_fails_config_loading() -> None:
    with pytest.raises(ConfigError, match="unknown key 'spec'"):
        Config.from_dict({**_BASE, "layout": {"spec": "specs"}}, source="c.toml")


# --------------------------------------------------------------------------- #
# LayoutRewriter: the prefix rewrite of synced text
# --------------------------------------------------------------------------- #


def test_the_default_layout_rewrites_nothing() -> None:
    rewriter = LayoutRewriter.for_layout({})

    assert not rewriter
    assert rewriter.rewrite("see `docs/specs/2026-01-01-x.md`") == (
        "see `docs/specs/2026-01-01-x.md`",
        (),
    )


def test_a_changed_key_rewrites_its_default_prefix_and_counts() -> None:
    rewriter = LayoutRewriter.for_layout({"specs": "specs"})

    text, counts = rewriter.rewrite(
        "Write `docs/specs/YYYY-MM-DD-<slug>.md`; specs live in docs/specs.\n"
        "Glob: docs/specs/**/*.md\n"
    )

    assert text == (
        "Write `specs/YYYY-MM-DD-<slug>.md`; specs live in specs.\nGlob: specs/**/*.md\n"
    )
    assert counts == (RewriteCount("docs/specs", "specs", 3),)


@pytest.mark.parametrize(
    "text",
    [
        "mydocs/specs/x.md",
        "other/docs/specs/x.md",
        "docs/specs-old/x.md",
        "docs/specs.md",
        "docs/specsheet",
        "my_docs/specs/x",
    ],
)
def test_only_a_whole_path_prefix_is_rewritten(text: str) -> None:
    assert LayoutRewriter.for_layout({"specs": "specs"}).rewrite(text) == (text, ())


def test_a_file_key_rewrites_the_whole_file_path() -> None:
    rewriter = LayoutRewriter.for_layout({"glossary": "docs/CONTEXT.md"})

    text, counts = rewriter.rewrite("Read CONTEXT.md, not CONTEXT-MAP.md or MY_CONTEXT.md.")

    assert text == "Read docs/CONTEXT.md, not CONTEXT-MAP.md or MY_CONTEXT.md."
    assert counts == (RewriteCount("CONTEXT.md", "docs/CONTEXT.md", 1),)


def test_a_dot_slash_spelling_is_rewritten_too() -> None:
    text, _ = LayoutRewriter.for_layout({"scratch": "tmp/scratch"}).rewrite("in ./.scratch/x")

    assert text == "in ./tmp/scratch/x"


def test_rewrites_never_chain() -> None:
    rewriter = LayoutRewriter.for_layout({"specs": "docs/plans", "plans": "docs/specs"})

    text, _ = rewriter.rewrite("docs/specs/a docs/plans/b")

    assert text == "docs/plans/a docs/specs/b"


def test_an_alias_maps_its_prefix_even_with_the_default_layout() -> None:
    rewriter = LayoutRewriter.for_layout({}, aliases={"docs/superpowers/plans/": "plans"})

    text, counts = rewriter.rewrite("Save to `docs/superpowers/plans/2026-x.md`.")

    assert text == "Save to `docs/plans/2026-x.md`."
    assert counts == (RewriteCount("docs/superpowers/plans", "docs/plans", 1),)


def test_an_alias_follows_the_configured_directory() -> None:
    rewriter = LayoutRewriter.for_layout(
        {"plans": "plans"}, aliases={"docs/superpowers/plans/": "plans"}
    )

    text, _ = rewriter.rewrite("docs/superpowers/plans/x.md and docs/plans/y.md")

    assert text == "plans/x.md and plans/y.md"


# prU L0-28: a configured path that extends its own default (docs/specs -> docs/specs/v2).


def test_a_path_extending_its_default_is_not_doubled() -> None:
    rewriter = LayoutRewriter.for_layout({"specs": "docs/specs/v2"})

    text, counts = rewriter.rewrite("docs/specs/x.md, docs/specs/v2/y.md and docs/specs/v2.")

    assert text == "docs/specs/v2/x.md, docs/specs/v2/y.md and docs/specs/v2."
    assert counts == (RewriteCount("docs/specs", "docs/specs/v2", 1),)


@pytest.mark.parametrize("key", LAYOUT_KEYS)
def test_rewriting_is_idempotent_on_every_layout_key(key: str) -> None:
    default = LAYOUT_DEFAULTS[key]
    rewriter = LayoutRewriter.for_layout({key: f"{default}/v2"})
    once, _ = rewriter.rewrite(f"see {default}, {default}/a.md and ./{default}/b\n")

    assert rewriter.rewrite(once) == (once, ())
    assert f"{default}/v2/v2" not in once


def test_an_alias_extending_its_source_is_not_doubled() -> None:
    rewriter = LayoutRewriter.for_layout(
        {"plans": "docs/acme/plans/v2"}, aliases={"docs/acme/plans/": "plans"}
    )

    once, _ = rewriter.rewrite("docs/acme/plans/x.md")

    assert once == "docs/acme/plans/v2/x.md"
    assert rewriter.rewrite(once) == (once, ())
