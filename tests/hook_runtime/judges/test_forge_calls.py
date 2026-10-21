"""What a forge CLI or ``playbook forge`` command does, read from its words (specs/prF-forge-adapter.md §8).

``forge_call`` is the one reading every guard shares: the files a command
sends, whether it publishes a gist or snippet, pushes ``HEAD``'s branch, opens
a pull request or adds a git remote, and the hosts its words or environment
name. It reads the ``forge`` tables only, offline.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.forge.dialects import GITHUB, GITLAB
from coding_agent_playbook.hook_runtime.judges.forge_calls import (
    ForgeCall,
    credential_flags,
    forge_call,
)
from coding_agent_playbook.hook_runtime.shell.parse import parse_shell


def _call(command: str, env: dict[str, str] | None = None) -> ForgeCall | None:
    return forge_call(parse_shell(command, "posix", "/r").segments[-1], env)


def _read(command: str, env: dict[str, str] | None = None) -> ForgeCall:
    call = _call(command, env)
    assert call is not None
    return call


@pytest.mark.parametrize(
    ("command", "files"),
    [
        ("gh issue create --body-file body.md", ("body.md",)),
        ("gh -R o/r issue create -F body.md", ("body.md",)),  # a flag before the verb
        ("gh issue lock 3 --body-file x.md", ("x.md",)),  # a noun row covers a new verb
        ("glab mr update 3 --description-file d.md", ("d.md",)),
        ("glab issue create --description-file -", ()),  # stdin
        ("glab mr create --template ./t.md", ("./t.md",)),
        ("glab mr create --template Default", ()),  # a template name on the forge
        ("gh pr create --template ./t.md", ()),  # gh reads -T as a name only
        ("gh api x --input req.json -F a=@b.txt --field c=@- -f d=@e", ("req.json", "b.txt")),
        ("glab api x --form file=@up.bin", ("up.bin",)),
        ("gh release upload v1 a.zip b.zip#Label", ("a.zip", "b.zip")),
        ("glab release create v1 dist/app.tgz -F notes.md", ("notes.md", "dist/app.tgz")),
        ("glab ci run --variables-file A:a.txt -f vars.json", ("vars.json", "a.txt")),
        ("gh workflow run ci.yml -F cfg=@c.json", ("c.json",)),
        ("glab snippet create a.md b.md", ("a.md", "b.md")),
        ("gh gist create -", ()),
        ("playbook forge issue create --title t --body-file b.md", ("b.md",)),
        ("playbook forge pr create --title t --template .github/pr.md", (".github/pr.md",)),
        ("playbook forge issue view 3", ()),
    ],
)
def test_files_a_forge_command_sends(command: str, files: tuple[str, ...]) -> None:
    assert _read(command).files == files


@pytest.mark.parametrize(
    ("command", "pushes"),
    [
        ("glab mr create --fill", True),
        ("glab mr create -f", True),
        ("glab mr create -yf", True),  # a short flag inside a cluster
        ("glab mr create --push", True),
        ("glab mr create --push false", True),  # pflag: a bool takes no separate value
        ("glab mr create --fill --push=false", True),  # --fill always pushes (glab 1.115)
        ("glab mr create --recover", True),  # restores a saved push setting
        ("glab mr create --push=false -t t", False),
        ("glab mr create -t t -d d", False),
        ("glab mr update 3 -f", False),
        ("gh repo create app --source . --push", True),
        ("gh repo create app --private", False),
        ("glab repo create app", False),  # glab 1.115 has no --push
        ("gh pr create --fill", False),
        ("playbook forge pr create --title t", False),  # never pushes (Q43)
    ],
)
def test_pushes_heads_branch(command: str, pushes: bool) -> None:
    assert _read(command).pushes is pushes


@pytest.mark.parametrize(
    ("command", "opens", "remote", "snippet"),
    [
        ("gh pr create", True, False, False),
        ("glab mr new -t t", True, False, False),
        ("playbook forge pr create --title t", True, False, False),
        ("gh repo fork --remote", False, True, False),
        ("glab repo fork --remote", False, True, False),
        ("gh repo fork", False, False, False),
        ("gh repo create app --source .", False, True, False),
        ("glab repo create app", False, True, False),  # git remote add, whatever its flags
        ("gh gist new a.md", False, False, True),
        ("glab snippet new a.md", False, False, True),
    ],
)
def test_effects(command: str, opens: bool, remote: bool, snippet: bool) -> None:
    call = _read(command)

    assert (call.opens_pull_request, call.changes_remote, call.snippet) == (opens, remote, snippet)


@pytest.mark.parametrize(
    ("command", "env", "hosts"),
    [
        ("gh -R ghe.corp/o/r pr view 3", {}, ("ghe.corp",)),
        ("gh pr view 3 -R o/r", {}, ()),
        ("gh api --hostname ghe.corp user", {}, ("ghe.corp",)),
        ("glab -R https://gitlab.corp/g/r mr view 3", {}, ("gitlab.corp",)),
        ("glab -R git@gitlab.corp:g/r.git mr view 3", {}, ("gitlab.corp",)),
        ("glab -R group/sub/repo mr view 3", {}, ()),  # GROUP/NAMESPACE/REPO
        ("glab -R gitlab.corp/g/r mr view 3", {}, ("gitlab.corp",)),  # dotted: a host
        ("glab -R gitlab.com/g/r mr view 3", {}, ("gitlab.com",)),
        ("glab -R git.corp/g/r mr view 3", {"GITLAB_HOST": "git.corp"}, ("git.corp",)),
        ("GITLAB_HOST=https://git.corp:8443 glab mr list", {}, ("git.corp",)),
        ("glab mr list", {"GL_HOST": "git.corp"}, ("git.corp",)),  # the hook's environment
        ("GITLAB_HOST=a.corp glab mr list", {"GITLAB_HOST": "b.corp"}, ("a.corp",)),
        ("glab mr list", {"GITLAB_API_HOST": "api.corp"}, ("api.corp",)),
        ("glab mr list", {"GITLAB_REPO": "https://git.x/g/r"}, ("git.x",)),
        ("gh pr list", {"GH_HOST": "ghe.corp"}, ("ghe.corp",)),
        ("gh pr list", {"GH_REPO": "ghe.corp/o/r"}, ("ghe.corp",)),
        ("gh pr list", {"GH_REPO": "o/r"}, ()),
        ("gh pr list -R o/r", {"GH_REPO": "127.0.0.1/o/r"}, ()),  # -R wins over GH_REPO
        ("gh pr list -R o/r", {"GH_HOST": "ghe.corp"}, ("ghe.corp",)),
        ("gh pr list", {"GITLAB_HOST": "git.corp"}, ()),  # another forge's variable
        ("playbook forge pr view 3", {"GH_HOST": "ghe.corp"}, ()),  # it sets the host itself
    ],
)
def test_hosts_the_command_or_its_environment_names(
    command: str, env: dict[str, str], hosts: tuple[str, ...]
) -> None:
    assert _read(command, env).hosts == hosts


@pytest.mark.parametrize(
    ("command", "contacts"),
    [
        ("gh pr view 3", True),
        ("glab version", False),
        ("gh help pr", False),
        ("gh pr view --help", False),
        ("glab config set editor vim", False),
        ("playbook forge which", False),  # reads git config only
        ("playbook forge auth status", True),
    ],
)
def test_contacts_forge(command: str, contacts: bool) -> None:
    assert _read(command).contacts_forge is contacts


@pytest.mark.parametrize(
    ("command", "reads"),
    [
        # prF §14: forge read operations print forge-hosted content (taint:forge)
        ("gh issue view 3", True),
        ("gh -R o/r pr view 3 --comments", True),
        ("gh pr diff 3", True),
        ("gh pr co 3", True),  # gh's alias of pr checkout
        ("gh issue ls --label bug", True),
        ("gh api repos/o/r/issues/3/comments", True),
        ("glab mr view 3", True),
        ("glab issue show 3", True),
        ("glab mr list", True),
        ("glab ci status", True),
        ("glab ci get --merge-request 3 -F json", True),  # playbook forge pr checks
        ("glab api projects/1/issues", True),
        ("playbook forge issue view 3", True),
        ("playbook forge -C ../app pr list --state open", True),
        ("playbook forge ref view '#3'", True),
        ("playbook forge pr checks 3", True),
        ("playbook forge issue blockers 3", True),  # gh issue view; glab api
        ("gh issue create --title t --body b", False),
        ("glab mr create --fill", False),
        ("gh auth status", False),  # the user's own login, no forge-hosted content
        ("playbook forge auth status", False),
        ("playbook forge which", False),
        ("playbook forge pr create --title t", False),
        ("gh issue view --help", False),
        ("glab mr view -h", False),
    ],
)
def test_reads_marks_forge_read_operations(command: str, reads: bool) -> None:
    assert _read(command).reads is reads


@pytest.mark.parametrize(
    ("command", "sends"),
    [
        # inline text, stdin or a file: a body, description, message, comment, notes or API field
        ("gh issue comment 3 --body 'looks good'", True),
        ("gh issue comment 3 -b ok", True),
        ("gh pr comment 3 -F -", True),  # the body on stdin
        ("gh pr comment 3 --body-file review.md", True),
        ("gh -R o/r pr review 3 --comment -b nit", True),
        ("gh issue close 3 --comment done", True),
        ("gh pr close 3 -c superseded", True),
        ("gh issue create -t t -b text", True),
        ("gh issue edit 3 --body=text", True),
        ("gh pr create -t t --body text", True),
        ("gh release create v1 --notes text", True),
        ("gh api repos/o/r/issues/3/comments -f body=text", True),
        ("gh api repos/o/r/issues --input -", True),
        ("glab issue note 3 -m text", True),
        ("glab mr note 3 --message=text", True),
        ("glab mr create -t t -d text", True),
        ("glab issue update 3 --description text", True),
        ("glab release create v1 -N text", True),
        ("glab api projects/1/issues -F title=x", True),
        ("playbook forge issue comment 3 --body text", True),
        ("playbook forge pr create --title t --body-file -", True),
        ("playbook forge issue close 3", True),  # kind sends_data
        ("gh issue view 3", False),
        ("gh issue edit 3 --add-label bug", False),
        ("gh pr review 3 --approve", False),
        ("glab mr create --push=false -t t", False),  # a title alone
        ("glab issue update 3 --label bug", False),
        ("gh api repos/o/r/issues", False),
        ("playbook forge issue label 3 --add bug", False),
        ("playbook forge pr view 3", False),
        ("gh issue comment 3 --help", False),
    ],
)
def test_sends_data_marks_text_and_files_sent_to_the_forge(command: str, sends: bool) -> None:
    assert _read(command).sends_data is sends


@pytest.mark.parametrize(
    "command",
    ["gh pr create --help", "glab mr create --fill -h", "gh help repo create", "glab version"],
)
def test_help_and_local_runs_do_nothing_on_the_forge(command: str) -> None:
    call = _read(command)

    assert (call.contacts_forge, call.pushes, call.opens_pull_request, call.files) == (
        False,
        False,
        False,
        (),
    )


def test_a_value_taking_dash_h_is_no_help() -> None:
    call = _read("gh repo create app -h https://x.example --source . --push")

    assert (call.contacts_forge, call.pushes) == (True, True)


def test_the_forge_and_command_shown() -> None:
    glab, gh, playbook = (
        _read("glab mr new"),
        _read("gh -R o/r pr view 3"),
        _read("coding-agent-playbook forge -C ../app pr list"),
    )

    assert (glab.forge, glab.command) == (GITLAB, "glab mr new")
    assert (gh.forge, gh.command) == (GITHUB, "gh pr view")
    assert (playbook.forge, playbook.command) == (None, "playbook forge pr list")


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "playbook sync",
        "playbook forge frobnicate",
        "echo glab snippet create a.md",
        "$GH pr create",  # an argv0 nobody can read
    ],
)
def test_other_commands_are_no_forge_call(command: str) -> None:
    assert _call(command) is None


def test_credential_flags_name_a_forge_clis_token_flags() -> None:
    assert credential_flags(["/usr/bin/glab", "auth", "login"]) == {
        "-t",
        "--token",
        "-j",
        "--job-token",
    }
    assert credential_flags(["glab", "mr", "create", "-t", "x"]) == frozenset()
    assert credential_flags(["mysql", "-p"]) == frozenset()
    assert credential_flags([]) == frozenset()
