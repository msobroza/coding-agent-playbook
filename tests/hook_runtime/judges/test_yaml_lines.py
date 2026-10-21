"""The YAML line helpers the gate-weakening judges share (specs/prF-forge-adapter.md §10.3, §14)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.hook_runtime.judges._yaml_lines import unquoted, without_comment


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("x: 1  # why", "x: 1"),
        ("# all comment", ""),
        ('echo "a # b"', 'echo "a # b"'),
        ("echo 'a # b'  # c", "echo 'a # b'"),
        ("url: a#b", "url: a#b"),
    ],
)
def test_without_comment_keeps_hashes_inside_quotes_or_words(text: str, expected: str) -> None:
    assert without_comment(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('"spec, test"', "spec, test"),
        ("'x'", "x"),
        ('"half', '"half'),
        ("'a\"", "'a\""),
        ('"', '"'),
    ],
)
def test_unquoted_drops_one_matching_pair_only(text: str, expected: str) -> None:
    assert unquoted(text) == expected
