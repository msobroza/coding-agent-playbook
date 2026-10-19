"""network-egress-guard: egress only to the approved hosts (specs/prK-hook-pack.md §E.5).

The engine ships the guard inert (``tier: overlay``, ``mode: off``); every
behavior test activates it through the regulated fixture overlay, which
promotes it to ``tier: default`` + ``mandatory: true`` with the §E.5 example
config (``mode: enforce``; ``artifactory.bank.example`` and ``git.bank.example``
allowed, ``litellm.bank.example`` the gateway), layered over the engine
definition by the real §A.6 merge. Each call is a real ``playbook-hook simulate
pre_tool_use``. ``FakeGit`` answers ``git remote -v``; the DNS spy proves no
host is ever resolved.
"""

from __future__ import annotations

import json
import socket
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.adapters.claude_code._overlay_native import network_native_rows
from coding_agent_playbook.hook_runtime.config.schema import GUARD_CONFIG_REL
from coding_agent_playbook.hook_runtime.dispatch.combine import ASK_DENIED_PREFIX
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.dispatch.event import Harness
from coding_agent_playbook.hook_runtime.dispatch.policy import UNATTENDED_ENV_VAR
from coding_agent_playbook.hook_runtime.dispatch.registry import load_builtin
from tests.hook_payloads import load_hook_payload
from tests.hook_runtime.fakes import FakeGit
from tests.hook_samples import resolved_hook

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.diagnostics.simulate import SimulateReport
    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
    from tests.hook_runtime.handlers.pack_repo import PackRepo

    type Deps = Callable[..., RuntimeDeps]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "network-egress-guard"
REMOTES: Final = {
    "origin": "https://git.bank.example/org/repo.git",
    "upstream": "https://github.com/org/repo.git",
}
LONG_QUERY: Final = "q=" + "a" * 298


@pytest.fixture
def repo(pack_repo: PackRepo, regulated_overlay: str) -> PackRepo:
    pack_repo.install_pack([HOOK_ID], overlays=(regulated_overlay,))
    return pack_repo


def _git() -> FakeGit:
    return FakeGit(remotes=dict(REMOTES))


def _bash(
    repo: PackRepo,
    deps: Deps,
    command: str,
    *,
    git: FakeGit | None = None,
    env: dict[str, str] | None = None,
) -> SimulateReport:
    payload = repo.tool_payload("Bash", {"command": command})
    return repo.simulate(payload, deps(git=git or _git()), env=env)


def _web(repo: PackRepo, deps: Deps, tool: str, tool_input: dict[str, Any]) -> SimulateReport:
    return repo.simulate(repo.tool_payload(tool, tool_input), deps(git=_git()))


def _golden(repo: PackRepo, deps: Deps, harness: str, case: str) -> SimulateReport:
    """Simulate golden ``case``; its decision, reason and wire output must match."""
    golden = load_hook_payload(harness, "pre_tool_use", case)
    report = repo.simulate(repo.relocate(golden), deps(git=_git()), harness=Harness(harness))
    expected = golden.expected["result"]
    combined = report.trace.combined
    assert (combined.decision.value, combined.reason) == (
        expected["decision"],
        expected.get("reason", ""),
    )
    assert report.trace.wire == golden.wire()
    return report


def _decision(report: SimulateReport) -> Decision:
    return report.trace.combined.decision


GOLDEN: Final[list[tuple[str, Decision]]] = [
    ("curl https://pypi.org/simple/", Decision.DENY),
    ("wget https://example.com/data.zip", Decision.DENY),
    ("curl https://artifactory.bank.example.evil.io/x", Decision.DENY),  # suffix, not substring
    ("curl https://api.artifactory.bank.example/v1", Decision.NONE),  # a subdomain
    ("curl https://litellm.bank.example/v1/models", Decision.NONE),  # the gateway
    ("curl http://localhost:8000/health", Decision.NONE),
    ("curl -s 'http://[::1]:9000/x'", Decision.NONE),
    ("nc -z 127.0.0.1 5432", Decision.NONE),
    ("ssh deploy@build.example", Decision.DENY),
    ("scp a.tar git.bank.example:/tmp", Decision.NONE),
    ("rsync -a out/ backup/", Decision.NONE),  # a local copy
    ('curl "$URL"', Decision.ASK),  # a destination nobody can read
    ("pip install -i https://artifactory.bank.example/simple requests", Decision.NONE),
    ("pip install --index-url=https://pypi.org/simple requests", Decision.DENY),
    ("uv pip install --extra-index-url https://download.pytorch.org/whl torch", Decision.DENY),
    ("pip install 'tool @ git+https://github.com/org/tool.git'", Decision.DENY),
    ("npm install --registry https://artifactory.bank.example/npm left-pad", Decision.NONE),
    ("pip install requests", Decision.ASK),  # the configured index: invisible to a hook
    ("uvx ruff check .", Decision.ASK),  # a runner launcher installs too
    ("uv sync", Decision.NONE),  # the lockfile pins its sources
    ("git clone https://github.com/org/repo.git", Decision.DENY),
    ("git clone https://git.bank.example/org/repo.git", Decision.NONE),
    ("git clone ../local.git copy", Decision.NONE),
    ("git fetch", Decision.NONE),  # origin is internal
    ("git fetch --depth 1 origin main", Decision.NONE),
    ("git push origin main:release", Decision.NONE),  # a refspec is no scp host
    ("git push upstream main", Decision.DENY),
    ("git pull https://github.com/org/repo.git main", Decision.DENY),
    ("git ls-remote https://gitlab.com/x/y.git", Decision.DENY),
    ("git push ../backup.git main", Decision.NONE),
    ("git submodule update --init", Decision.ASK),  # .gitmodules is not read
    ("git submodule add https://github.com/org/lib.git vendor/lib", Decision.DENY),
    ("docker pull ubuntu:24.04", Decision.DENY),  # Docker Hub
    ("docker image pull --platform linux/amd64 ubuntu", Decision.DENY),
    ("docker pull artifactory.bank.example/team/app:1", Decision.NONE),
    ("docker pull artifactory.bank.example:5000/team/app:1", Decision.NONE),  # a port
    ("docker run --rm ubuntu true", Decision.NONE),  # not a pull
    ("huggingface-cli download bert-base-uncased", Decision.DENY),
    (
        "HF_ENDPOINT=https://artifactory.bank.example/hf huggingface-cli download bert",
        Decision.NONE,
    ),
    ("huggingface-cli env", Decision.NONE),  # local
    ("echo curl https://pypi.org", Decision.NONE),
    ("ls -la && git status", Decision.NONE),
]


@pytest.mark.parametrize(("command", "expected"), GOLDEN)
def test_golden(repo: PackRepo, deps: Deps, command: str, expected: Decision) -> None:
    assert _decision(_bash(repo, deps, command)) is expected


@pytest.mark.parametrize("harness", ["claude_code", "opencode"])
def test_enforce_curl_pypi_denied(repo: PackRepo, deps: Deps, harness: str) -> None:
    report = _golden(repo, deps, harness, "neg_bash_curl_pypi")

    assert report.trace.wire.exit_code == 10
    assert report.trace.combined.outcomes[0].rule_id == "host"


@pytest.mark.parametrize("harness", ["claude_code", "opencode"])
def test_pip_install_from_allowlisted_index_allowed(
    repo: PackRepo, deps: Deps, harness: str
) -> None:
    _golden(repo, deps, harness, "neg_bash_pip_internal_index")


@pytest.mark.parametrize("harness", ["claude_code", "opencode"])
def test_websearch_denied_in_enforce(repo: PackRepo, deps: Deps, harness: str) -> None:
    report = _golden(repo, deps, harness, "neg_websearch")

    assert report.trace.combined.outcomes[0].rule_id == "websearch"


@pytest.mark.parametrize("harness", ["claude_code", "opencode"])
def test_webfetch_allowlisted_with_long_query_asks(
    repo: PackRepo, deps: Deps, harness: str
) -> None:
    """An ask on Claude; OpenCode cannot ask, so the same verdict is denied there."""
    report = _golden(repo, deps, harness, "neg_webfetch_long_query")

    assert report.trace.combined.outcomes[0].rule_id == "webfetch_query"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://artifactory.bank.example/docs/index.html", Decision.NONE),
        (f"https://artifactory.bank.example/x?{LONG_QUERY[:256]}", Decision.NONE),  # at the cap
        ("http://localhost:8080/x", Decision.NONE),
        ("https://docs.python.org/3/", Decision.DENY),
        ("not a url", Decision.DENY),
    ],
)
def test_webfetch_host_and_query_rows(
    repo: PackRepo, deps: Deps, url: str, expected: Decision
) -> None:
    assert _decision(_web(repo, deps, "WebFetch", {"url": url, "prompt": "p"})) is expected


def test_loopback_and_gateway_hosts_allowed(repo: PackRepo, deps: Deps) -> None:
    commands = [
        "curl http://localhost:4000/v1",
        "curl http://127.0.0.2/x",
        "curl https://litellm.bank.example/v1/chat/completions",
    ]

    assert {_decision(_bash(repo, deps, command)) for command in commands} == {Decision.NONE}


def test_reasons_name_the_host_and_never_list_the_allowlist(repo: PackRepo, deps: Deps) -> None:
    denied = _bash(repo, deps, "curl https://pypi.org/simple/")
    asked = _bash(repo, deps, "pip install requests")

    assert denied.trace.combined.reason == (
        'Blocked: `curl` would contact "pypi.org", which is not an approved host.\n'
        "Use the approved internal hosts (internal index or mirror); do not retry public hosts."
    )
    assert asked.trace.combined.reason == (
        "`pip install` fetches from the configured package index, which this guard cannot "
        "see.\nConfirm with the user."
    )
    for report in (denied, asked):
        assert "bank.example" not in report.trace.combined.reason  # internal names stay out


def test_getaddrinfo_never_called(
    repo: PackRepo, deps: Deps, monkeypatch: pytest.MonkeyPatch
) -> None:
    lookups: list[Any] = []

    def spy(*args: Any, **kwargs: Any) -> Any:
        lookups.append(args)
        raise AssertionError("a guard resolved a host name")

    monkeypatch.setattr(socket, "getaddrinfo", spy)
    monkeypatch.setattr(socket, "gethostbyname", spy)

    decisions = [_decision(_bash(repo, deps, command)) for command, _ in GOLDEN]
    fetched = _web(repo, deps, "WebFetch", {"url": "https://docs.python.org/3/", "prompt": "p"})

    assert decisions == [expected for _, expected in GOLDEN]
    assert _decision(fetched) is Decision.DENY
    assert lookups == []


def test_git_remotes_read_only_for_a_remote_name(repo: PackRepo, deps: Deps) -> None:
    by_url, by_name, off_git = _git(), _git(), _git()

    _bash(repo, deps, "git clone https://github.com/org/repo.git", git=by_url)
    _bash(repo, deps, "git push upstream main", git=by_name)
    _bash(repo, deps, "curl https://pypi.org && ls", git=off_git)

    assert (by_url.calls, off_git.calls) == ([], [])
    assert [method for method, _ in by_name.calls] == ["remote_urls"]


def test_unparsed_network_command_asks(repo: PackRepo, deps: Deps) -> None:
    assert _decision(_bash(repo, deps, "curl 'https://pypi.org")) is Decision.ASK
    assert _decision(_bash(repo, deps, "echo 'unterminated")) is Decision.NONE


def test_ask_mode_asks_and_degrades_to_deny_unattended(
    pack_repo: PackRepo, regulated_overlay: str, deps: Deps
) -> None:
    pack_repo.install_pack(
        [HOOK_ID], overlays=(regulated_overlay,), handler_config={HOOK_ID: {"mode": "ask"}}
    )

    attended = _bash(pack_repo, deps, "curl https://pypi.org/simple/")
    search = _web(pack_repo, deps, "WebSearch", {"query": "q"})
    unattended = _bash(
        pack_repo, deps, "curl https://pypi.org/simple/", env={UNATTENDED_ENV_VAR: "1"}
    )

    assert [_decision(r) for r in (attended, search)] == [Decision.ASK, Decision.ASK]
    assert attended.trace.combined.reason == (
        '`curl` would contact "pypi.org", which is not an approved host.\nConfirm with the user.'
    )
    assert _decision(unattended) is Decision.DENY
    assert unattended.trace.combined.reason.startswith(ASK_DENIED_PREFIX)


def test_mode_off_is_inert_and_renders_no_native_rows(
    pack_repo: PackRepo, regulated_overlay: str, deps: Deps
) -> None:
    pack_repo.install_pack(
        [HOOK_ID], overlays=(regulated_overlay,), handler_config={HOOK_ID: {"mode": "off"}}
    )
    off = {"mode": "off", "allowed_hosts": ["artifactory.bank.example"], "gateway_hosts": []}

    curl = _bash(pack_repo, deps, "curl https://pypi.org/simple/")
    search = _web(pack_repo, deps, "WebSearch", {"query": "q"})

    assert [_decision(r) for r in (curl, search)] == [Decision.NONE, Decision.NONE]
    assert network_native_rows([resolved_hook(HOOK_ID, config=off)]) == {}


def test_guard_config_states_the_mode_for_the_briefing(repo: PackRepo) -> None:
    """The session briefing reports ``guard_config.network.mode`` (§E.1 item 8, §E.5)."""
    document = json.loads((repo.root / GUARD_CONFIG_REL).read_bytes())

    assert document["network"] == {"mode": "enforce"}
    assert document["hooks"][HOOK_ID]["mandatory"] is True


def test_declares_the_network_domain_and_no_prefilter() -> None:
    """``[guardrails.network]`` feeds it (§B.3); runner launchers defeat an argv0 prefilter."""
    declaration = load_builtin("network_egress_guard")

    assert declaration.config_domain == "network"
    assert declaration.config_schema["mode"].order == ("off", "ask", "enforce")
    assert declaration.config_schema["mode"].policy == "strictest"
    assert {k for k, v in declaration.config_schema.items() if v.policy == "relax"} == {
        "allowed_hosts",
        "gateway_hosts",
        "webfetch_max_query_chars",
    }
    assert declaration.argv0s is None
