"""``forge.dialects``: each forge CLI's tables, pinned against the guard rows of spec prF §8."""

from __future__ import annotations

import pytest

from coding_agent_playbook.forge.dialects import (
    FORGES,
    GITHUB,
    GITLAB,
    CliCommand,
    Forge,
    by_cli,
    by_name,
)


def _row(forge: Forge, *words: str) -> CliCommand:
    row = forge.command(words)
    assert row is not None, f"{forge.cli} {' '.join(words)} has no row"
    return row


def test_the_forges_are_github_then_gitlab() -> None:
    assert [(forge.name, forge.host, forge.cli) for forge in FORGES] == [
        ("github", "github.com", "gh"),
        ("gitlab", "gitlab.com", "glab"),
    ]


@pytest.mark.parametrize(
    ("argv0", "forge"), [("gh", GITHUB), ("glab", GITLAB), ("git", None), ("", None)]
)
def test_by_cli_finds_the_forge_of_an_argv0(argv0: str, forge: Forge | None) -> None:
    assert by_cli(argv0) is forge


@pytest.mark.parametrize(
    ("name", "forge"), [("github", GITHUB), ("gitlab", GITLAB), ("GitLab", None), ("", None)]
)
def test_by_name_finds_the_forge_a_forge_hosts_value_names(name: str, forge: Forge | None) -> None:
    assert by_name(name) is forge


@pytest.mark.parametrize(
    ("forge", "words", "path"),
    [
        (GITLAB, ["mr", "create", "--fill"], ("mr", "create")),
        (GITLAB, ["mr", "new", "-t", "x"], ("mr", "create")),
        (GITLAB, ["mr", "note", "create", "3", "--attach", "f"], ("mr", "note")),
        (GITLAB, ["mr", "comment", "3", "--attach", "f"], ("mr", "note")),
        (GITLAB, ["mr", "merge", "3"], ("mr",)),
        (GITHUB, ["issue", "transfer", "3", "o/r"], ("issue",)),
        (GITHUB, ["gist", "new", "a.txt"], ("gist", "create")),
        (GITHUB, ("pr", "create"), ("pr", "create")),
    ],
)
def test_command_finds_the_longest_matching_row(
    forge: Forge, words: list[str], path: tuple[str, ...]
) -> None:
    assert _row(forge, *words).paths[0] == path


@pytest.mark.parametrize("words", [[], ["status"], ["--version"], ["gist"], ["Issue", "create"]])
def test_command_is_none_for_a_command_no_guard_reads(words: list[str]) -> None:
    assert GITHUB.command(words) is None


# --- §8.2 egress rows -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("forge", "words"),
    [
        (GITHUB, ("gist", "create")),
        (GITHUB, ("gist", "new")),
        (GITLAB, ("snippet", "create")),
        (GITLAB, ("snippet", "new")),
    ],
)
def test_a_gist_or_snippet_publishes_its_file_operands(
    forge: Forge, words: tuple[str, ...]
) -> None:
    row = _row(forge, *words)

    assert row.snippet is True
    assert row.file_operands == 0


@pytest.mark.parametrize(
    ("words", "flags"),
    [
        (("issue", "create"), {"--description-file", "--attach"}),
        (("issue", "new"), {"--description-file", "--attach"}),
        (("issue", "update"), {"--description-file", "--attach"}),
        (("mr", "create"), {"--description-file", "--attach"}),
        (("mr", "update"), {"--description-file", "--attach"}),
        (("issue", "note"), {"--attach"}),
        (("issue", "comment"), {"--attach"}),
        (("mr", "note"), {"--attach"}),
        (("mr", "note", "create"), {"--attach"}),
        (("release", "create"), {"-F", "--notes-file", "--experimental-notes-text-or-file"}),
        (("release", "edit"), {"-F", "--notes-file"}),
        (("api",), {"--input"}),
        (("ci", "run"), {"-f", "--variables-from"}),
    ],
)
def test_glab_sends_the_file_of_a_body_file_flag(words: tuple[str, ...], flags: set[str]) -> None:
    assert _row(GITLAB, *words).files == flags


@pytest.mark.parametrize(
    ("words", "flags"),
    [
        (("issue", "create"), {"-F", "--body-file"}),
        (("issue", "comment"), {"-F", "--body-file"}),
        (("issue", "edit"), {"-F", "--body-file"}),
        (("issue", "close"), {"-F", "--body-file"}),
        (("pr", "create"), {"-F", "--body-file"}),
        (("pr", "comment"), {"-F", "--body-file"}),
        (("pr", "edit"), {"-F", "--body-file"}),
        (("pr", "review"), {"-F", "--body-file"}),
        (("pr", "merge"), {"-F", "--body-file"}),
        (("release", "create"), {"-F", "--notes-file"}),
        (("release", "edit"), {"-F", "--notes-file"}),
        (("api",), {"--input"}),
    ],
)
def test_gh_sends_the_file_of_a_body_file_flag(words: tuple[str, ...], flags: set[str]) -> None:
    assert _row(GITHUB, *words).files == flags


@pytest.mark.parametrize(
    ("forge", "words", "flags"),
    [
        (GITHUB, ("api",), {"-F", "--field"}),  # gh 2.94 has no --form
        (GITLAB, ("api",), {"-F", "--field", "--form"}),
        (GITHUB, ("workflow", "run"), {"-F", "--field"}),
    ],
)
def test_field_flags_send_an_at_file(forge: Forge, words: tuple[str, ...], flags: set[str]) -> None:
    assert _row(forge, *words).field_files == flags


def test_a_glab_pipeline_file_variable_sends_its_file() -> None:
    assert _row(GITLAB, "ci", "run").keyed_files == {"--variables-file"}


@pytest.mark.parametrize(
    ("forge", "words", "flags"),
    [
        # gh 2.94 matches -T against its template list by name: never a local path
        (GITHUB, ("issue", "create"), set()),
        (GITHUB, ("pr", "create"), set()),
        (GITLAB, ("issue", "create"), {"--template"}),
        (GITLAB, ("mr", "create"), {"--template"}),
        (GITHUB, ("api",), set()),
    ],
)
def test_template_flags_are_body_files_when_path_shaped(
    forge: Forge, words: tuple[str, ...], flags: set[str]
) -> None:
    assert _row(forge, *words).templates == flags


@pytest.mark.parametrize(
    ("forge", "words"),
    [
        (GITHUB, ("release", "create")),
        (GITHUB, ("release", "new")),
        (GITHUB, ("release", "upload")),
        (GITLAB, ("release", "create")),
        (GITLAB, ("release", "upload")),
    ],
)
def test_release_assets_follow_the_tag(forge: Forge, words: tuple[str, ...]) -> None:
    row = _row(forge, *words)

    assert row.file_operands == 1
    assert row.snippet is False


@pytest.mark.parametrize(
    ("forge", "words", "remotes"),
    [
        (GITHUB, ("repo", "fork"), {"--remote"}),
        (GITLAB, ("repo", "fork"), {"--remote"}),
        (GITHUB, ("repo", "create"), {"-s", "--source"}),
        (GITLAB, ("repo", "create"), set()),
    ],
)
def test_fork_and_create_name_their_remote_flags(
    forge: Forge, words: tuple[str, ...], remotes: set[str]
) -> None:
    assert _row(forge, *words).remotes == remotes


@pytest.mark.parametrize("forge", FORGES)
def test_repo_create_creates_a_repository(forge: Forge) -> None:
    assert _row(forge, "repo", "create").creates_repository is True


def test_the_host_env_vars_are_the_guards_host_sources() -> None:
    env = {var for forge in FORGES for var in (*forge.host_env, *forge.api_host_env)}

    assert env == {"GH_HOST", "GITLAB_HOST", "GL_HOST", "GITLAB_URI", "GITLAB_API_HOST"}
    assert GITLAB.host_env == ("GITLAB_HOST", "GITLAB_URI", "GL_HOST")


@pytest.mark.parametrize("forge", FORGES)
def test_repo_and_hostname_flags_name_the_forge_host(forge: Forge) -> None:
    assert forge.repo_flags == {"-R", "--repo"}
    assert forge.hostname_flags == {"--hostname"}
    assert forge.hostname_flags <= _row(forge, "api").values


def test_each_forge_cli_reads_its_token_from_its_env_vars() -> None:
    assert GITHUB.token_env == (
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "GH_ENTERPRISE_TOKEN",
        "GITHUB_ENTERPRISE_TOKEN",
    )
    assert GITLAB.token_env == ("GITLAB_TOKEN", "GITLAB_ACCESS_TOKEN", "OAUTH_TOKEN")


# --- §8.3 pushes and pull requests -------------------------------------------------------------


@pytest.mark.parametrize(
    ("forge", "words", "flags"),
    [
        (GITLAB, ("mr", "create"), {"-f", "--fill", "--push", "--recover"}),
        (GITLAB, ("mr", "new"), {"-f", "--fill", "--push", "--recover"}),
        (GITHUB, ("repo", "create"), {"--push"}),
        (GITLAB, ("repo", "create"), set()),  # glab 1.115 has no repo create --push
        (GITHUB, ("pr", "create"), set()),
        (GITLAB, ("mr", "update"), set()),
    ],
)
def test_a_pushing_flag_pushes_heads_branch(
    forge: Forge, words: tuple[str, ...], flags: set[str]
) -> None:
    assert _row(forge, *words).pushes == flags


def test_glab_repo_create_adds_a_remote_whatever_its_flags() -> None:
    glab, gh = _row(GITLAB, "repo", "create"), _row(GITHUB, "repo", "create")

    assert (glab.adds_remote, gh.adds_remote) == (True, False)


@pytest.mark.parametrize(
    ("forge", "words", "opens"),
    [
        (GITHUB, ("pr", "create"), True),
        (GITHUB, ("pr", "new"), True),
        (GITLAB, ("mr", "create"), True),
        (GITLAB, ("mr", "new"), True),
        (GITHUB, ("pr", "edit"), False),
        (GITLAB, ("mr", "update"), False),
    ],
)
def test_opening_a_pull_request(forge: Forge, words: tuple[str, ...], opens: bool) -> None:
    assert _row(forge, *words).opens_pull_request is opens


# --- §8.4 push options, Q55/Q56 markers and credentials -------------------------------------


@pytest.mark.parametrize(
    ("option", "effect"),
    [
        ("secret_push_protection.skip_all", "skips_secret_detection"),
        ("secret_detection.skip_all", "skips_secret_detection"),
        ("security_policy.bypass_reason=hotfix", "bypasses_security_policy"),
        ("ci.variable=DEPLOY=1", "sets_ci_input"),
        ("ci.input=env=prod", "sets_ci_input"),
        ("ci.skip", "skips_ci"),
        ("ci.no_pipeline", "skips_ci"),
        ("integrations.skip_ci", "skips_ci"),
        ("merge_request.create", "opens_pull_request"),
        ("merge_request.description=see notes", "sends_text"),
        ("merge_request.target=main", None),
        ("mr.create", "opens_pull_request"),  # the server's alias of merge_request
        ("mr.description=x", "sends_text"),
        ("secret_push_protection .skip_all", "skips_secret_detection"),  # parts are stripped
        (" mr . create", "opens_pull_request"),
        ("mr", None),
        ("CI.SKIP", None),
        ("", None),
    ],
)
def test_gitlab_push_options(option: str, effect: str | None) -> None:
    assert GITLAB.push_option(option) == effect


def test_a_gist_lands_on_its_own_host_and_a_snippet_on_the_repos() -> None:
    assert (GITHUB.snippet_name, GITHUB.snippet_host) == ("gist", "gist.github.com")
    assert (GITLAB.snippet_name, GITLAB.snippet_host) == ("snippet", "")


def test_github_reads_no_push_option() -> None:
    assert GITHUB.push_options == ()
    assert GITHUB.push_option("ci.skip") is None


def test_gitlab_markers_skip_secret_detection_or_ci() -> None:
    assert GITLAB.secret_skip_markers == (
        "[skip secret push protection]",
        "[skip secret detection]",  # legacy: GitGuardian still reads it
    )
    assert GITLAB.skip_ci_markers == ("[skip ci]", "[ci skip]", "[skip pipeline]", "[no ci]")
    assert (GITHUB.secret_skip_markers, GITHUB.skip_ci_markers) == ((), ())


def test_glab_auth_login_token_values_are_secrets() -> None:
    row = _row(GITLAB, "auth", "login")

    assert row.secrets == {"-t", "--token", "-j", "--job-token"}
    assert row.secrets <= row.values


# --- invariants the guards rely on -------------------------------------------------------------


_ROWS = [(forge, row) for forge in FORGES for row in forge.commands]
_IDS = [f"{forge.cli} {' '.join(row.paths[0])}" for forge, row in _ROWS]


@pytest.mark.parametrize(("forge", "row"), _ROWS, ids=_IDS)
def test_values_hold_every_value_taking_flag(forge: Forge, row: CliCommand) -> None:
    carried = row.files | row.field_files | row.keyed_files | row.templates | row.secrets

    assert carried | row.options == row.values
    assert not row.options & carried


@pytest.mark.parametrize(("forge", "row"), _ROWS, ids=_IDS)
def test_a_flag_that_pushes_takes_no_value(forge: Forge, row: CliCommand) -> None:
    # split_words would read a value-taking --fill's next word as its value
    assert not row.pushes & row.values


@pytest.mark.parametrize("forge", FORGES)
def test_no_two_rows_share_a_path(forge: Forge) -> None:
    paths = [path for row in forge.commands for path in row.paths]

    assert len(paths) == len(set(paths))


@pytest.mark.parametrize("forge", FORGES)
def test_every_flag_is_spelled_as_a_flag(forge: Forge) -> None:
    flags = {flag for row in forge.commands for flag in (*row.values, *row.pushes, *row.remotes)}

    assert sorted(flag for flag in flags if not flag.startswith("-") or " " in flag) == []
