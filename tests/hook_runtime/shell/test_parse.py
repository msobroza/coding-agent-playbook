"""The shell parser behind every Bash guard (specs/prK-lifecycle-hooks.md §D.2.5, §D.9).

Guards judge the *effective* command, so the red-team rows map an input to the
argv, wrappers and dynamic indexes a guard sees. ``parse_shell`` is pure: it
executes and expands nothing, and needs no fixture.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.hook_runtime.shell.parse import (
    LIMIT,
    MAX_SEGMENTS,
    MAX_TEXT_BYTES,
    Redirect,
    Segment,
    ShellCommand,
    ShellConfig,
    parse_shell,
    write_targets,
)
from tests.import_probe import new_modules_after

_PROXY = ShellConfig(wrapper_prefixes=("proxy run", "proxy"))


def _parse(text: str, *, cwd: str | None = "/r", cfg: ShellConfig = _PROXY) -> ShellCommand:
    return parse_shell(text, "posix", cwd, cfg)


def _argvs(text: str) -> list[tuple[str, ...]]:
    return [segment.argv for segment in _parse(text).segments]


def _only(text: str, *, cfg: ShellConfig = _PROXY) -> Segment:
    command = _parse(text, cfg=cfg)
    assert command.parse_error is None
    assert len(command.segments) == 1, command.segments
    return command.segments[0]


# --- the §D.9 red-team table ----------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "index", "expected"),
    [
        pytest.param(
            "proxy git push --force origin main",
            0,
            {"argv": ("git", "push", "--force", "origin", "main"), "wrappers": ("proxy",)},
            id="proxy-prefix",
        ),
        pytest.param(
            "env FOO=1 sudo -u root timeout 5 rm -rf /",
            0,
            {
                "argv": ("rm", "-rf", "/"),
                "wrappers": ("env", "sudo", "timeout"),
                "env": (("FOO", "1"),),
                "raw_argv": (
                    "env",
                    "FOO=1",
                    "sudo",
                    "-u",
                    "root",
                    "timeout",
                    "5",
                    "rm",
                    "-rf",
                    "/",
                ),
            },
            id="env-sudo-timeout",
        ),
        pytest.param(
            "bash -lc 'rm -rf ~'",
            1,
            {"argv": ("rm", "-rf", "~"), "wrappers": ("bash",), "origin": "bash_c", "depth": 1},
            id="bash-lc",
        ),
        pytest.param(
            "xargs rm -rf < list",
            0,
            {
                "argv": ("rm", "-rf"),
                "wrappers": ("xargs",),
                "origin": "xargs",
                "args_open": True,
                "redirects": (Redirect("<", "list", None),),
            },
            id="xargs",
        ),
        pytest.param(
            "find . -name x -exec rm {} \\;",
            1,
            {"argv": ("rm", "{}"), "origin": "find_exec", "args_open": True, "wrappers": ("find",)},
            id="find-exec",
        ),
        pytest.param(
            'rm -rf "$(pwd)"/x',
            1,
            {"argv": ("rm", "-rf", "$(pwd)/x"), "dynamic": frozenset({2}), "origin": "top"},
            id="dynamic-subst",
        ),
    ],
)
def test_effective_argv_red_team(text: str, index: int, expected: dict[str, object]) -> None:
    command = _parse(text)

    assert command.parse_error is None
    segment = command.segments[index]
    for name, value in expected.items():
        assert getattr(segment, name) == value, name


def test_find_itself_stays_a_segment_for_delete() -> None:
    assert _argvs("find . -name x -exec rm {} \\;")[0] == (
        "find",
        ".",
        "-name",
        "x",
        "-exec",
        "rm",
        "{}",
        ";",
    )
    assert _argvs("find . -exec rm {} + -execdir sh -c 'rm -rf x' \\;") == [
        ("find", ".", "-exec", "rm", "{}", "+", "-execdir", "sh", "-c", "rm -rf x", ";"),
        ("rm", "{}"),
        ("sh", "-c", "rm -rf x"),
        ("rm", "-rf", "x"),
    ]


def test_command_substitution_is_parsed_first_as_a_subst_segment() -> None:
    segments = _parse('rm -rf "$(pwd)"/x `cat list`').segments

    assert [(s.argv, s.origin, s.depth) for s in segments] == [
        (("pwd",), "subst", 1),
        (("cat", "list"), "subst", 1),
        (("rm", "-rf", "$(pwd)/x", "`cat list`"), "top", 0),
    ]
    assert segments[2].dynamic == frozenset({2, 3})


@pytest.mark.parametrize(
    ("text", "argv", "dynamic"),
    [
        (
            "echo $HOME ${USER:-x} $1 $((1 + 2))",
            ("echo", "$HOME", "${USER:-x}", "$1", "$((1 + 2))"),
            {1, 2, 3, 4},
        ),
        ("echo '$HOME' \"\\$HOME\" \\$HOME", ("echo", "$HOME", "$HOME", "$HOME"), set()),
        ('echo "a $X b"', ("echo", "a $X b"), {1}),
        ("rm -rf $'\\x2f'", ("rm", "-rf", "/"), set()),
        ("echo $'it\\'s' $\"hi\"", ("echo", "it's", "hi"), set()),
        ("diff <(ls a) >(cat)", ("diff", "<(ls a)", ">(cat)"), {1, 2}),
        ("echo a\\\nb 'c d'\"e\"", ("echo", "ab", "c de"), set()),
        ('echo $ "$"', ("echo", "$", "$"), set()),
        ("echo a \\\n b", ("echo", "a", "b"), set()),
        (r"echo $'\101'", ("echo", "A"), set()),
    ],
)
def test_quotes_and_expansions(text: str, argv: tuple[str, ...], dynamic: set[int]) -> None:
    segment = _parse(text).segments[-1]

    assert segment.argv == argv
    assert segment.dynamic == frozenset(dynamic)


def test_substitutions_nested_in_expansions_still_become_segments() -> None:
    argvs = _argvs(
        r'echo ${X:-$(rm -rf a)} $(( $(rm -rf b) + 1 )) "`rm -rf c`" ${Y:-`rm -rf d`} ${Z:-\}}'
    )

    for name in "abcd":
        assert ("rm", "-rf", name) in argvs
    assert argvs[-1][-1] == r"${Z:-\}}"


def test_backquote_escapes_nest_a_second_substitution() -> None:
    segments = _parse(r"echo `echo \`rm -rf z\` \$HOME`").segments

    assert [(s.argv, s.depth) for s in segments] == [
        (("rm", "-rf", "z"), 2),
        (("echo", "`rm -rf z`", "$HOME"), 1),
        (("echo", r"`echo \`rm -rf z\` \$HOME`"), 0),
    ]


# --- heredocs -------------------------------------------------------------------------


def test_heredoc_body_is_data_never_parsed() -> None:
    command = _parse('git commit -m "mentions -n" <<EOF\nskip hooks: --no-verify\nEOF\necho done')

    assert [s.argv for s in command.segments] == [
        ("git", "commit", "-m", "mentions -n"),
        ("echo", "done"),
    ]
    assert command.segments[0].heredoc_bodies == ("skip hooks: --no-verify\n",)
    assert command.segments[0].redirects == (Redirect("<<", None, None),)


def test_claude_commit_heredoc_inside_substitution_is_one_argument() -> None:
    text = (
        "git commit -m \"$(cat <<'EOF'\nfix(x): don't (1) parse\n\nBody --no-verify\nEOF\n)\""
        " && git push"
    )

    command = _parse(text)

    assert command.parse_error is None
    cat, commit, push = command.segments
    assert (cat.argv, cat.origin) == (("cat",), "subst")
    assert cat.heredoc_bodies == ("fix(x): don't (1) parse\n\nBody --no-verify\n",)
    assert commit.argv[:3] == ("git", "commit", "-m")
    assert commit.argv[3].startswith("$(cat <<'EOF'")
    assert commit.dynamic == frozenset({3})
    assert push.argv == ("git", "push")


def test_unquoted_heredoc_substitutions_run_and_are_parsed() -> None:
    command = _parse("cat <<EOF\n" + r"safe $(rm -rf x) \$(not run) `rm -rf y`" + "\nEOF")

    assert [(s.argv, s.origin) for s in command.segments] == [
        (("rm", "-rf", "x"), "subst"),
        (("rm", "-rf", "y"), "subst"),
        (("cat",), "top"),
    ]


def test_quoted_heredoc_is_pure_data_and_dash_strips_tabs() -> None:
    quoted = _only("cat <<'EOF'\n$(rm -rf x)\nEOF")
    dashed = _only("cat <<-END\n\tbody\n\tEND")
    unterminated = _only("cat <<EOF\nrest")

    assert quoted.heredoc_bodies == ("$(rm -rf x)\n",)
    assert dashed.heredoc_bodies == ("body\n",)
    assert unterminated.heredoc_bodies == ("rest\n",)
    assert _only("cat <<EOF").heredoc_bodies == ("",)


# --- degradation ----------------------------------------------------------------------


def test_unbalanced_quote_sets_parse_error_with_regex_split_fallback() -> None:
    command = _parse("echo 'oops && rm -rf /")

    assert command.parse_error is not None
    assert command.parse_error != LIMIT
    assert [s.argv for s in command.segments] == [("echo", "'oops"), ("rm", "-rf", "/")]
    assert command.segments[1].cwd == "/r"


@pytest.mark.parametrize(
    "text",
    [
        'echo "open',
        "echo `open",
        "echo $(open",
        "echo ${open",
        "echo $((1 + 2",
        "echo $'open",
        "echo trailing\\",
        "cat >",
        "echo \ue000",
    ],
)
def test_every_scanner_failure_degrades_to_parse_error(text: str) -> None:
    command = _parse(text)

    assert command.parse_error is not None
    assert command.segments[0].argv[0] in {"echo", "cat"}


def test_more_than_256_segments_sets_limit() -> None:
    command = _parse("true; " * (MAX_SEGMENTS + 44))

    assert command.parse_error == LIMIT
    assert len(command.segments) == MAX_SEGMENTS


@pytest.mark.parametrize(
    "text",
    [
        "echo $(echo $(echo $(echo $(echo $(echo deep)))))",
        "proxy env sudo nice timeout 5 nohup rm -rf /",
        "x" * (MAX_TEXT_BYTES + 1),
    ],
    ids=["nesting", "wrappers", "text"],
)
def test_every_limit_sets_limit(text: str) -> None:
    assert _parse(text).parse_error == LIMIT


@pytest.mark.parametrize(("opener", "closer"), [("$((", "))"), ("${", "}")])
@pytest.mark.parametrize("levels", [5, 2000])
def test_nested_expansions_count_toward_the_depth_limit(
    opener: str, closer: str, levels: int
) -> None:
    """Regression: nested ``$((`` / ``${`` once recursed unbounded into a RecursionError."""
    text = "echo " + opener * levels + "1" + closer * levels

    assert _parse(text).parse_error == LIMIT
    assert _parse("echo " + opener * 4 + "1" + closer * 4).parse_error is None


def test_four_levels_of_nesting_are_within_the_limit() -> None:
    command = _parse("echo $(echo $(echo $(echo $(echo deep))))")

    assert command.parse_error is None
    assert command.segments[0].depth == 4


def test_powershell_is_never_shlex_parsed() -> None:
    command = parse_shell("Remove-Item -Recurse -Force C:\\proj", "powershell", "C:/proj", _PROXY)

    assert (command.segments, command.parse_error, command.kind) == ((), None, "powershell")
    assert command.text == "Remove-Item -Recurse -Force C:\\proj"


# --- wrappers -------------------------------------------------------------------------


@pytest.mark.parametrize("prefixes", [("proxy run", "proxy"), ("proxy", "proxy run")])
def test_wrapper_prefixes_longest_prefix_strip(prefixes: tuple[str, ...]) -> None:
    cfg = ShellConfig(wrapper_prefixes=prefixes)

    proxy = _only("proxy run git push", cfg=cfg)
    plain = _only("/opt/bin/proxy git status", cfg=cfg)

    assert (proxy.argv, proxy.wrappers) == (("git", "push"), ("proxy run",))
    assert (plain.argv, plain.wrappers) == (("git", "status"), ("proxy",))
    assert _only("proxy git status", cfg=ShellConfig()).argv[0] == "proxy"
    assert _only("proxy", cfg=cfg).argv == ("proxy",)


@pytest.mark.parametrize(
    ("text", "argv", "wrapper"),
    [
        ("uv run mypy src", ("mypy", "src"), "uv run"),
        ("uv run --frozen --no-sync -p 3.12 --with ruff pytest -q", ("pytest", "-q"), "uv run"),
        ("uvx --from ruff==0.8 ruff check", ("ruff", "check"), "uvx"),
        ("poetry run -C sub pytest", ("pytest",), "poetry run"),
        ("pdm run --project x lint", ("lint",), "pdm run"),
        ("hatch run test", ("test",), "hatch run"),
        ("pipx run --spec black==24 black .", ("black", "."), "pipx run"),
    ],
)
def test_runner_wrappers_kept_in_wrappers(text: str, argv: tuple[str, ...], wrapper: str) -> None:
    segment = _only(text)

    assert (segment.argv, segment.wrappers) == (argv, (wrapper,))
    assert _only(text, cfg=ShellConfig(runner_wrappers=())).argv == segment.raw_argv


@pytest.mark.parametrize(
    ("text", "argv", "wrappers"),
    [
        ("sudo -E -u root -- rm x", ("rm", "x"), ("sudo",)),
        ("sudo -iu root", (), ("sudo",)),
        ("sudo --login", (), ("sudo",)),
        ("doas -s", (), ("doas",)),
        ("sudo -l", ("sudo", "-l"), ()),
        ("sudo FOO=1 rm x", ("rm", "x"), ("sudo",)),
        ("command -p rm x", ("rm", "x"), ("command",)),
        ("command -v rm", ("command", "-v", "rm"), ()),
        ("exec -a name rm x", ("rm", "x"), ("exec",)),
        ("nohup rm x", ("rm", "x"), ("nohup",)),
        ("time -p rm x", ("rm", "x"), ("time",)),
        ("nice -n 5 rm x", ("rm", "x"), ("nice",)),
        ("nice -10 rm x", ("rm", "x"), ("nice",)),
        ("ionice -c 2 -n 7 rm x", ("rm", "x"), ("ionice",)),
        ("stdbuf -oL rm x", ("rm", "x"), ("stdbuf",)),
        ("timeout -s KILL --preserve-status 5s rm x", ("rm", "x"), ("timeout",)),
        ("xargs -0 -I {} rm {}", ("rm", "{}"), ("xargs",)),
        ("xargs", ("echo",), ("xargs",)),
        ("env -i -u HOME rm x", ("rm", "x"), ("env",)),
        ("env -S 'rm -rf /'", ("rm", "-rf", "/"), ("env",)),
        ("env --split-string='rm x'", ("rm", "x"), ("env",)),
        ("env - rm x", ("rm", "x"), ("env",)),
        ("env -i -- rm x", ("rm", "x"), ("env",)),
        ("env '-Srm -rf /'", ("rm", "-rf", "/"), ("env",)),
        ("env FOO=1", ("env", "FOO=1"), ()),
        ("/usr/bin/sudo rm x", ("rm", "x"), ("sudo",)),
        ('"$RUNNER" rm x', ("$RUNNER", "rm", "x"), ()),
    ],
)
def test_wrapper_table(text: str, argv: tuple[str, ...], wrappers: tuple[str, ...]) -> None:
    segment = _only(text)

    assert (segment.argv, segment.wrappers) == (argv, wrappers)


def test_an_unsplittable_env_split_string_degrades() -> None:
    assert _parse('env -S "rm \'x"').parse_error is not None


def test_env_assignments_collect_from_the_shell_and_from_env() -> None:
    segment = _only("A=1 B='x y' env C=3 sudo D=4 rm x")

    assert segment.env == (("A", "1"), ("B", "x y"), ("C", "3"), ("D", "4"))
    assert segment.argv == ("rm", "x")
    assert _only('"A=1" rm').argv == ("A=1", "rm")


def test_nested_shells_and_eval_inherit_the_outer_chain() -> None:
    segments = _parse("sudo bash -c 'eval \"rm -rf /tmp/x\"'").segments

    assert [(s.argv, s.wrappers, s.origin, s.depth) for s in segments] == [
        (("bash", "-c", 'eval "rm -rf /tmp/x"'), ("sudo",), "top", 0),
        (("eval", "rm -rf /tmp/x"), ("sudo", "bash"), "bash_c", 1),
        (("rm", "-rf", "/tmp/x"), ("sudo", "bash", "eval"), "eval", 2),
    ]


@pytest.mark.parametrize(
    "text", ["bash script.sh", "bash -s", "sh", "bash -o pipefail", "eval", "bash -c"]
)
def test_shells_without_a_c_script_are_opaque(text: str) -> None:
    assert _argvs(text) == [tuple(text.split())]


def test_shell_options_before_the_script_are_skipped() -> None:
    assert _argvs("bash -e -o pipefail +o posix --norc -c 'rm x' arg0")[1] == ("rm", "x")


def test_xargs_args_open_flows_into_nested_shells() -> None:
    segments = _parse("xargs -I{} sh -c 'rm {}'").segments

    assert [(s.argv, s.args_open) for s in segments] == [
        (("sh", "-c", "rm {}"), True),
        (("rm", "{}"), True),
    ]


# --- segments, groups and cwd ---------------------------------------------------------


def test_control_operators_set_pipes_and_background() -> None:
    segments = _parse("curl x | sh & echo a |& cat; b && c || d\ne").segments

    assert [(s.argv[0], s.pipes_to_next, s.background) for s in segments] == [
        ("curl", True, False),
        ("sh", False, True),
        ("echo", True, False),
        ("cat", False, False),
        ("b", False, False),
        ("c", False, False),
        ("d", False, False),
        ("e", False, False),
    ]


def test_groups_keywords_and_comments_are_stripped() -> None:
    text = (
        "{ rm a; } && (rm b) # rm commented\n"
        "if test -f x; then rm c; else rm d; fi\n"
        "while true; do ! rm e; done < input"
    )

    argvs = _argvs(text)

    assert argvs == [
        ("rm", "a"),
        ("rm", "b"),
        ("test", "-f", "x"),
        ("rm", "c"),
        ("rm", "d"),
        ("true",),
        ("rm", "e"),
        (),
    ]
    assert _parse(text).segments[-1].redirects == (Redirect("<", "input", None),)
    assert _only('"if" x').argv == ("if", "x")


@pytest.mark.parametrize(
    ("text", "cwd", "expected"),
    [
        ("cd sub && rm a", "/r", "/r/sub"),
        ("cd sub; rm a", "/r", "/r/sub"),
        ("cd sub\nrm a", "/r", "/r/sub"),
        ("cd sub || rm a", "/r", "/r"),
        ("cd sub | rm a", "/r", "/r"),
        ("cd sub & rm a", "/r", "/r"),
        ("cd -P /abs/x && rm a", "/r", "/abs/x"),
        ("cd .. && rm a", "/r/s", "/r"),
        ("cd sub && cd deeper && rm a", "/r", "/r/sub/deeper"),
        ("pushd sub && rm a", "/r", "/r/sub"),
        ('cd "$D" && rm a', "/r", None),
        ("cd && rm a", "/r", None),
        ("cd - && rm a", "/r", None),
        ("cd ~/x && rm a", "/r", None),
        ("cd sub && rm a", None, None),
        ("cd /abs && rm a", None, "/abs"),
        ("cd -- sub && rm a", "/r", "/r/sub"),
    ],
)
def test_cd_and_sets_segment_cwd(text: str, cwd: str | None, expected: str | None) -> None:
    segments = _parse(text, cwd=cwd).segments

    assert segments[0].cwd == cwd
    assert segments[-1].cwd == expected


def test_a_subshell_cd_ends_at_its_closing_paren() -> None:
    segments = _parse("(cd sub && rm a); rm b; echo $(cd x && pwd) && rm c").segments

    assert [(s.argv, s.cwd) for s in segments] == [
        (("cd", "sub"), "/r"),
        (("rm", "a"), "/r/sub"),
        (("rm", "b"), "/r"),
        (("cd", "x"), "/r"),
        (("pwd",), "/r/x"),
        (("echo", "$(cd x && pwd)"), "/r"),
        (("rm", "c"), "/r"),
    ]


# --- write_targets --------------------------------------------------------------------


def _targets(text: str) -> list[str]:
    return [target for segment in _parse(text).segments for target in write_targets(segment)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("echo x > out", ["out"]),
        ("echo x >> log", ["log"]),
        ("echo x >| f", ["f"]),
        ("cmd &> all", ["all"]),
        ("cmd &>> all", ["all"]),
        ("cmd 2> err 2>&1 >&-", ["err"]),
        ("cmd >& both", ["both"]),
        ("cat < in <> rw", ["rw"]),
        ("echo x | tee -a a.txt b.txt", ["a.txt", "b.txt"]),
        ("sed -i 's/a/b/' f1 f2", ["f1", "f2"]),
        ("sed -i.bak -e 's/a/b/' f", ["f"]),
        ("sed -i '' -e 's/a/b/' f", ["f"]),
        ("sed --in-place --expression=s/a/b/ f", ["f"]),
        ("sed -ni -f prog.sed f", ["f"]),
        ("sed -n 's/a/b/p' f", []),
        ("sed -i -- 's/a/b/' -f", ["-f"]),
        ("perl -pi -e 's/a/b/' f", ["f"]),
        ("perl -i.bak -pe 's/a/b/' f", ["f"]),
        ("perl -pi script.pl f", ["f"]),
        ("perl -I lib -e 'print 1' f", []),
        ("cp AGENTS.md /tmp/x", ["/tmp/x"]),
        ("cp -r -S .bak a b dest/", ["dest/"]),
        ("cp -t dest a b", ["dest"]),
        ("mv --target-directory=dest a", ["dest"]),
        ("mv --target-directory dest a", ["dest"]),
        ("cp a -- -t", ["-t"]),
        ("mv a b", ["b"]),
        ("mv a", []),
        ("install -m 644 src dst", ["dst"]),
        ("install -d d1 d2", ["d1", "d2"]),
        ("rm -rf a b", ["a", "b"]),
        ("rm -- -weird", ["-weird"]),
        ("truncate -s 0 f", ["f"]),
        ("dd if=/dev/zero of=disk.img bs=1M", ["disk.img"]),
        ("cat <<EOF > out\nx\nEOF", ["out"]),
        ("sudo tee /etc/hosts", ["/etc/hosts"]),
        ("> empty", ["empty"]),
        ("{ echo a; } > grp", ["grp"]),
        ("bash -c 'echo x' > out", ["out"]),
        ("ls -la", []),
    ],
)
def test_write_targets(text: str, expected: list[str]) -> None:
    assert _targets(text) == expected


def test_dynamic_redirect_targets_are_flagged() -> None:
    segment = _only('echo x > "$OUT"')

    assert segment.redirects == (Redirect(">", "$OUT", None, dynamic=True),)
    assert write_targets(segment) == ["$OUT"]


# --- import-light ---------------------------------------------------------------------

_FORBIDDEN = {"jinja2", "yaml", "importlib.metadata", "tomllib", "packaging", "argparse", "json"}


def test_shell_parse_and_git_command_import_only_the_stdlib_and_the_runtime() -> None:
    loaded = new_modules_after(
        "import coding_agent_playbook.hook_runtime.shell.parse, coding_agent_playbook.hook_runtime.shell.git_command"
    )

    engine = {name for name in loaded if name.startswith("coding_agent_playbook")}
    runtime = "coding_agent_playbook.hook_runtime"
    assert {
        name for name in engine if name != runtime and not name.startswith(f"{runtime}.")
    } == set()
    assert "coding_agent_playbook.hook_runtime.shell.parse" in engine
    assert not _FORBIDDEN & set(loaded)
