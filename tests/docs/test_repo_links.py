"""Repo-path links rewritten to their site pages (docs/_ext/repo_links.py)."""

from __future__ import annotations

import pytest

from repo_links import rewrite_repo_links

_BLOB = "https://example.test/blob/main/"


@pytest.mark.parametrize(
    ("text", "docname", "expected"),
    [
        ("[home](../README.md)", "checks", "[home](index.md)"),
        ("[home](../../README.md#install)", "adr/0001-x", "[home](../index.md#install)"),
        ("[glossary](../CONTEXT.md)", "setup", "[glossary](glossary.md)"),
        ("[guide](../catalog/README.md)", "skills", "[guide](contributing.md)"),
        ("[adrs](adr/)", "overview", "[adrs](adr/index.md)"),
        ("[spec](../SPEC.md#9-3)", "overview", f"[spec]({_BLOB}SPEC.md#9-3)"),
    ],
)
def test_links_to_repo_files_point_at_their_site_home(
    text: str, docname: str, expected: str
) -> None:
    assert rewrite_repo_links(text, docname=docname, blob_url=_BLOB) == expected


@pytest.mark.parametrize(
    "text",
    [
        "[forge](checks.md#playbook-forge)",
        "[site](https://example.test/README.md)",
        "[anchor](#readme)",
        "[other](../pyproject.toml)",
    ],
)
def test_other_links_are_left_for_myst(text: str) -> None:
    assert rewrite_repo_links(text, docname="checks", blob_url=_BLOB) == text


def test_without_a_forge_a_repository_only_file_is_named_as_text() -> None:
    text = "[Read SPEC.md](../SPEC.md#9-3)."

    assert (
        rewrite_repo_links(text, docname="design-spec", blob_url="") == "Read SPEC.md (`SPEC.md`)."
    )
