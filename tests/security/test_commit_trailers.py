"""git-commit-push-policy-guard's trailer rows, shared with ``check-commit-trailers`` (specs/prK-hook-pack.md §E.4)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.security.commit_trailers import (
    GitPolicy,
    commit_msg_violations,
    trailer_block,
)

MESSAGE = (
    "feat: parse the config\n"
    "\n"
    "Co-Authored-By: in the body is prose, not a trailer\n"
    "\n"
    "Refs: AB-12\n"
    "Co-authored-by: Ada Lovelace <ada@corp.test>\n"
)


def test_trailer_block_is_last_paragraph_only() -> None:
    assert trailer_block(MESSAGE) == [
        ("Refs", "AB-12"),
        ("Co-authored-by", "Ada Lovelace <ada@corp.test>"),
    ]
    assert trailer_block("Refs: AB-12\n") == []  # the subject is never a trailer block


def test_trailer_block_drops_comments_scissors_and_folds_continuations() -> None:
    message = (
        "fix: x\n\nRefs: AB-1\n  AB-2\n# Please enter the commit message\n"
        "# ------------------------ >8 ------------------------\n\nSigned-off-by: a <a@x>\n"
    )

    assert trailer_block(message) == [("Refs", "AB-1 AB-2")]


def test_cp401_forbidden_trailer_case_insensitive() -> None:
    policy = GitPolicy(forbid_trailers=("CO-AUTHORED-BY",))

    assert commit_msg_violations(MESSAGE, policy) == ["CP401 forbidden trailer Co-authored-by"]
    assert commit_msg_violations("feat: x\n\nbody\n", policy) == []


def test_cp402_coauthor_not_in_allowlist() -> None:
    by_email = GitPolicy(allowed_coauthors=("ADA@corp.test",))
    by_name = GitPolicy(allowed_coauthors=("Ada Lovelace <ada@corp.test>",))
    other = GitPolicy(allowed_coauthors=("bob@corp.test",))

    assert commit_msg_violations(MESSAGE, by_email) == []
    assert commit_msg_violations(MESSAGE, by_name) == []
    assert commit_msg_violations(MESSAGE, other) == [
        "CP402 co-author not in allowed_coauthors: Ada Lovelace <ada@corp.test>"
    ]


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (MESSAGE, []),
        ("feat: x\n\nRefs: none\n", ["CP403 trailer Refs does not match ^[A-Z]+-\\d+$"]),
        ("feat: x\n\nbody only\n", ["CP403 missing required trailer Refs"]),
    ],
)
def test_cp403_required_trailer_regex(message: str, expected: list[str]) -> None:
    policy = GitPolicy(required_trailers=(("Refs", r"^[A-Z]+-\d+$"),))

    assert commit_msg_violations(message, policy) == expected


def test_cp403_trailer_keys_compare_case_insensitively() -> None:
    policy = GitPolicy(required_trailers=(("refs", r"^[A-Z]+-\d+$"),))

    assert commit_msg_violations(MESSAGE, policy) == []


def test_cp403_unsafe_pattern_is_reported_not_run() -> None:
    policy = GitPolicy(required_trailers=(("Refs", "(a+)+$"),))

    (line,) = commit_msg_violations(MESSAGE, policy)

    assert line.startswith("CP403 required trailer Refs: regex '(a+)+$' nests unbounded")


def test_empty_rows_report_nothing() -> None:
    assert GitPolicy().has_rows is False
    assert commit_msg_violations(MESSAGE, GitPolicy()) == []


def test_policy_from_config_keeps_well_shaped_rows_only() -> None:
    policy = GitPolicy.from_config(
        {
            "forbid_trailers": ["Co-Authored-By", 3, ""],
            "allowed_coauthors": "not-a-list",
            "required_trailers": {"Refs": "^X-\\d+$", "Bad": 1},
        }
    )

    assert policy == GitPolicy(
        forbid_trailers=("Co-Authored-By",), required_trailers=(("Refs", "^X-\\d+$"),)
    )
