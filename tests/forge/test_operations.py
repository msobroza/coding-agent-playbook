"""``forge.operations``: the forge-operation catalogue, pinned against spec prF §6.3 and §8."""

from __future__ import annotations

from dataclasses import replace

import pytest

from coding_agent_playbook.forge.dialects import FORGES, GITHUB, GITLAB, Forge
from coding_agent_playbook.forge.operations import (
    BODY_FILE,
    BODY_OPTIONS,
    OPERATIONS,
    Operation,
    OperationCall,
    operation_call,
)


def _operation(name: str) -> Operation:
    (found,) = [candidate for candidate in OPERATIONS if candidate.name == name]
    return found


@pytest.mark.parametrize(
    ("words", "name", "args", "directory"),
    [
        (["issue", "create", "--title", "x"], "issue create", ("--title", "x"), None),
        (["-C", "../app", "pr", "view", "3"], "pr view", ("3",), "../app"),
        (["-C../app", "--json", "pr", "view", "3"], "pr view", ("3",), "../app"),
        (["-C", "a", "-C", "b", "which"], "which", (), "b"),
        (["which", "--json"], "which", ("--json",), None),
        (["auth", "status"], "auth status", (), None),
    ],
)
def test_operation_call_reads_the_operation_after_the_global_options(
    words: list[str], name: str, args: tuple[str, ...], directory: str | None
) -> None:
    assert operation_call(words) == OperationCall(_operation(name), args, directory)


@pytest.mark.parametrize(
    "words",
    [
        [],
        ["issue"],
        ["issue", "delete", "3"],
        ["secret", "set"],
        ["-C"],
        ["--json"],
        ["mr", "create"],
    ],
)
def test_operation_call_is_none_for_no_operation(words: list[str]) -> None:
    assert operation_call(words) is None


#: Spec §6.3, row by row: (operation, kind, positionals, GitHub argv, GitLab argv or None).
_CATALOGUE = [
    ("issue create", "sends_data", (), ("issue", "create"), ("issue", "create")),
    ("issue view", "read", ("n",), ("issue", "view"), ("issue", "view")),
    ("issue list", "read", (), ("issue", "list"), ("issue", "list")),
    ("issue comment", "sends_data", ("n",), ("issue", "comment"), ("api",)),
    ("issue label", "write", ("n",), ("issue", "edit"), ("issue", "update")),
    ("issue close", "sends_data", ("n",), ("issue", "close"), ("issue", "close")),
    ("issue assign", "write", ("n",), ("issue", "edit"), ("issue", "update")),
    ("issue edit", "sends_data", ("n",), ("issue", "edit"), ("issue", "update")),
    ("issue link-child", "write", ("parent", "child"), ("issue", "edit"), None),
    ("issue children", "read", ("parent",), ("issue", "view"), None),
    ("issue block", "write", ("child", "blocker"), ("issue", "edit"), ("api",)),
    ("issue blockers", "read", ("n",), ("issue", "view"), ("api",)),
    ("label list", "read", (), ("label", "list"), ("label", "list")),
    ("label create", "write", ("name",), ("label", "create"), ("label", "create")),
    ("pr create", "sends_data", (), ("pr", "create"), ("mr", "create")),
    ("pr view", "read", ("n",), ("pr", "view"), ("mr", "view")),
    ("pr list", "read", (), ("pr", "list"), ("mr", "list")),
    ("pr diff", "read", ("n",), ("pr", "diff"), ("mr", "diff")),
    ("pr checkout", "read", ("n",), ("pr", "checkout"), ("mr", "checkout")),
    ("pr comment", "sends_data", ("n",), ("pr", "comment"), ("mr", "note", "create")),
    ("pr label", "write", ("n",), ("pr", "edit"), ("mr", "update")),
    ("pr close", "sends_data", ("n",), ("pr", "close"), ("mr", "close")),
    ("pr ready", "write", ("n",), ("pr", "ready"), ("mr", "update")),
    ("pr edit", "sends_data", ("n",), ("pr", "edit"), ("mr", "update")),
    ("pr checks", "read", ("n",), ("pr", "checks"), ("ci", "get")),
    ("ref view", "read", ("ref",), ("pr", "view"), ("issue", "view")),
    ("which", "read", (), (), ()),
    ("auth status", "read", (), ("auth", "status"), ("auth", "status")),
]


def test_the_catalogue_is_spec_section_6_3_in_order() -> None:
    assert [operation.name for operation in OPERATIONS] == [row[0] for row in _CATALOGUE]


@pytest.mark.parametrize(("name", "kind", "positionals", "github", "gitlab"), _CATALOGUE)
def test_each_operation_kind_arguments_and_forge_cli_words(
    name: str,
    kind: str,
    positionals: tuple[str, ...],
    github: tuple[str, ...],
    gitlab: tuple[str, ...] | None,
) -> None:
    operation = _operation(name)
    on_github = operation.translation(GITHUB)
    on_gitlab = operation.translation(GITLAB)

    assert (operation.kind, operation.positionals) == (kind, positionals)
    assert on_github is not None
    assert on_github.argv == github
    assert (None if on_gitlab is None else on_gitlab.argv) == gitlab


@pytest.mark.parametrize(
    ("name", "values", "flags"),
    [
        (
            "issue create",
            {
                "--title",
                "--body",
                "--body-file",
                "--template",
                "--label",
                "--assignee",
                "--parent",
                "--blocked-by",
            },
            {"--confidential"},
        ),
        ("issue view", set(), {"--comments"}),
        ("issue list", {"--state", "--label", "--assignee", "--search", "--limit"}, {"--no-label"}),
        ("issue comment", {"--body", "--body-file"}, set()),
        ("issue label", {"--add", "--remove"}, set()),
        ("issue close", {"--comment", "--reason"}, set()),
        ("issue assign", {"--add"}, set()),
        ("issue edit", {"--title", "--body", "--body-file"}, set()),
        ("label create", {"--color", "--description"}, set()),
        ("pr create", {"--title", "--body", "--body-file", "--template", "--base"}, {"--draft"}),
        ("pr view", set(), {"--comments"}),
        ("pr list", {"--state", "--label"}, {"--external"}),
        ("pr comment", {"--body", "--body-file", "--reply-to"}, set()),
        ("pr label", {"--add", "--remove"}, set()),
        ("pr close", {"--comment"}, set()),
        ("pr edit", {"--title", "--body", "--body-file"}, set()),
        ("which", set(), set()),
    ],
)
def test_each_operation_takes_its_spec_options(
    name: str, values: set[str], flags: set[str]
) -> None:
    operation = _operation(name)

    assert operation.values == values
    assert operation.flags == flags


def test_only_labels_repeat_and_only_states_and_a_close_reason_are_choices() -> None:
    assert {op.name: op.repeatable for op in OPERATIONS if op.repeatable} == {
        "issue create": {"--label"},
        "issue list": {"--label"},
    }
    assert {op.name: op.choices for op in OPERATIONS if op.choices} == {
        "issue list": (("--state", ("open", "closed", "all")),),
        "issue close": (("--reason", ("completed", "not-planned", "duplicate")),),
        "pr list": (("--state", ("open", "closed", "merged", "all")),),
    }


# --- what the guards read (spec §8.1) ----------------------------------------------------------


def test_the_operations_that_send_a_body_file() -> None:
    sending = [op.name for op in OPERATIONS if op.kind == "sends_data" and BODY_FILE in op.values]

    assert BODY_FILE == "--body-file"
    assert sending == [
        "issue create",
        "issue comment",
        "issue edit",
        "pr create",
        "pr comment",
        "pr edit",
    ]


def test_only_pr_create_opens_a_pull_request_and_nothing_pushes() -> None:
    assert [op.name for op in OPERATIONS if op.opens_pull_request] == ["pr create"]
    assert [op.name for op in OPERATIONS if op.kind == "pushes"] == []


def test_a_found_body_file_is_among_the_arguments() -> None:
    call = operation_call(
        ["-C", "app", "issue", "comment", "3", "--body-file", "notes.md", "--json"]
    )

    assert call is not None
    assert call.operation.kind == "sends_data"
    assert call.args == ("3", "--body-file", "notes.md", "--json")
    assert call.directory == "app"


# --- translations (spec §6.3 columns) ----------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "github", "gitlab"),
    [
        ("issue create", ("--body-file", "-"), ("--description-file", "-")),
        ("issue comment", ("--body-file", "-"), ()),
        ("issue edit", ("--body-file", "-"), ("--description-file", "-")),
        ("pr create", ("--body-file", "-"), ("--description-file", "-")),
        ("pr comment", ("--body-file", "-"), ()),
        ("pr edit", ("--body-file", "-"), ("--description-file", "-")),
    ],
)
def test_a_body_reaches_the_forge_cli_on_stdin(
    name: str, github: tuple[str, ...], gitlab: tuple[str, ...]
) -> None:
    on_github, on_gitlab = (
        _operation(name).translation(GITHUB),
        _operation(name).translation(GITLAB),
    )

    assert on_github is not None
    assert on_gitlab is not None
    assert (on_github.body, on_gitlab.body) == (github, gitlab)


def test_pr_create_never_pushes_on_gitlab() -> None:
    on_gitlab = _operation("pr create").translation(GITLAB)

    assert on_gitlab is not None
    assert on_gitlab.fixed == ("--push=false", "--yes")
    assert ("--base", "--target-branch") in on_gitlab.options
    assert "Q55" in on_gitlab.note


@pytest.mark.parametrize(
    ("name", "forge", "renames"),
    [
        ("issue label", GITHUB, (("--add", "--add-label"), ("--remove", "--remove-label"))),
        ("issue label", GITLAB, (("--add", "--label"), ("--remove", "--unlabel"))),
        ("pr label", GITHUB, (("--add", "--add-label"), ("--remove", "--remove-label"))),
        ("pr label", GITLAB, (("--add", "--label"), ("--remove", "--unlabel"))),
        ("issue assign", GITHUB, (("--add", "--add-assignee"),)),
        ("issue assign", GITLAB, (("--add", "--assignee"),)),
        (
            "issue list",
            GITLAB,
            (
                ("--label", "--label"),
                ("--assignee", "--assignee"),
                ("--search", "--search"),
                ("--limit", "--per-page"),
            ),
        ),
        (
            "pr create",
            GITLAB,
            (("--title", "--title"), ("--draft", "--draft"), ("--base", "--target-branch")),
        ),
        (
            "issue create",
            GITLAB,
            (
                ("--title", "--title"),
                ("--label", "--label"),
                ("--assignee", "--assignee"),
                ("--confidential", "--confidential"),
            ),
        ),
    ],
)
def test_options_reach_the_forge_cli_under_its_own_names(
    name: str, forge: Forge, renames: tuple[tuple[str, str], ...]
) -> None:
    translation = _operation(name).translation(forge)

    assert translation is not None
    assert translation.options == renames


@pytest.mark.parametrize(
    ("name", "forge", "unsupported", "paid"),
    [
        ("issue create", GITLAB, {"--parent"}, False),
        ("issue create", GITHUB, {"--confidential"}, False),
        ("issue block", GITLAB, set(), True),
        ("issue blockers", GITLAB, set(), True),
        ("issue block", GITHUB, set(), False),
    ],
)
def test_what_a_forge_or_its_plan_lacks_exits_3(
    name: str, forge: Forge, unsupported: set[str], paid: bool
) -> None:
    translation = _operation(name).translation(forge)

    assert translation is not None
    assert translation.unsupported == unsupported
    assert translation.paid is paid


@pytest.mark.parametrize(
    ("name", "github", "gitlab"),
    [
        ("issue view", ("--json",), ("-F", "json")),
        ("issue list", ("--json",), ("-O", "json")),
        ("label list", ("--json",), ("-F", "json")),
        ("pr view", ("--json",), ("-F", "json")),
        ("pr list", ("--json",), ("-F", "json")),
        ("pr diff", ("--color", "never"), ("--color", "never", "--raw")),
        ("pr ready", (), ("--ready",)),
        ("issue children", ("--json", "subIssues"), None),
        ("issue blockers", ("--json", "blockedBy"), ()),
    ],
)
def test_each_call_adds_its_fixed_forge_cli_words(
    name: str, github: tuple[str, ...], gitlab: tuple[str, ...] | None
) -> None:
    on_github, on_gitlab = (
        _operation(name).translation(GITHUB),
        _operation(name).translation(GITLAB),
    )

    assert on_github is not None
    assert on_github.fixed == github
    assert (None if on_gitlab is None else on_gitlab.fixed) == gitlab


# --- invariants ----------------------------------------------------------------------------------


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.name)
def test_every_operation_has_one_translation_per_forge(operation: Operation) -> None:
    assert [name for name, _ in operation.translations] == [forge.name for forge in FORGES]


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.name)
def test_translations_name_only_the_operations_own_options(operation: Operation) -> None:
    own = operation.values | operation.flags
    for forge in FORGES:
        translation = operation.translation(forge)
        if translation is None:
            continue
        assert {old for old, _ in translation.options} <= own
        assert translation.unsupported <= own
    assert operation.repeatable <= operation.values
    assert {option for option, _ in operation.choices} <= operation.values
    assert not operation.values & operation.flags


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.name)
def test_a_body_is_text_or_a_file(operation: Operation) -> None:
    assert ("--body" in operation.values) is (BODY_FILE in operation.values)


def test_translation_rejects_an_unknown_forge() -> None:
    other = replace(GITLAB, name="bitbucket")

    with pytest.raises(KeyError, match="'bitbucket'"):
        _operation("pr view").translation(other)


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.name)
def test_every_option_is_passed_unsupported_or_handled_by_the_note(operation: Operation) -> None:
    for forge in FORGES:
        translation = operation.translation(forge)
        if translation is None:
            continue
        passed = {option for option, _ in translation.options}
        handled = passed | translation.unsupported | BODY_OPTIONS
        unhandled = sorted(
            option
            for option in operation.values | operation.flags
            if option not in handled and option not in translation.note
        )
        assert unhandled == [], f"{forge.cli}: {unhandled}"


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.name)
def test_a_body_operation_says_how_the_body_reaches_stdin(operation: Operation) -> None:
    if not BODY_OPTIONS & operation.values:
        return
    for forge in FORGES:
        translation = operation.translation(forge)
        assert translation is not None
        assert translation.body or "stdin" in translation.note, forge.cli
