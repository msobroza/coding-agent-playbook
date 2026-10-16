"""The overlay-tier activation path end to end (specs/prK-hook-pack.md §E.5, Track K9 Done-when).

A synthetic consumer repo runs the real ``playbook sync`` and ``playbook
validate`` in-process (``FakeGitClient``, hermetic sync seams). The engine ships
pii-prompt-guard, network-egress-guard and sensitive-data-read-guard as
``tier: overlay`` with inert data, so nothing renders until the regulated
fixture overlay (``overlays_enabled``) promotes them; its network-egress-guard
is ``mandatory: true``, which no ``[hooks]`` switch and no consumer relax key
can loosen (H15, §A.6).
"""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.commands import validate as _validate
from tests.cli.hook_repo import GUARD_CONFIG, SETTINGS, hook_deps
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    SyntheticRepoFactory = Callable[..., Path]

pytestmark = pytest.mark.catalog

OVERLAY_IDS: Final = ("network-egress-guard", "pii-prompt-guard", "sensitive-data-read-guard")
NETWORK: Final = "network-egress-guard"
#: The fixture overlay's approved hosts (allowed, then the gateway).
OVERLAY_HOSTS: Final = ["artifactory.bank.example", "git.bank.example"]
_CONFIG: Final = """\
schema_version = 1
adapters_enabled = ["claude_code", "opencode"]
overlays_enabled = [{overlays}]

[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "0.1.0a0"

[storage]
artifact_source = "filesystem"
state_source = "filesystem"
{extra}"""
_HOOKS_ON: Final = "\n[hooks]\nenabled = true\n"


def _repo(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    *,
    overlay: str | None = None,
    extra: str = _HOOKS_ON,
) -> Path:
    overlays = f'"{overlay}"' if overlay else ""
    root = tmp_path / "repo"
    root.mkdir()
    return make_synthetic_repo(root, config_text=_CONFIG.format(overlays=overlays, extra=extra))


def _sync_repo(repo: Path, tmp_path: Path) -> int:
    return _sync.execute(repo, git=FakeGitClient(), hook_deps=hook_deps(tmp_path / "state"))


def _validate_repo(repo: Path) -> int:
    return _validate.run(argparse.Namespace(repo_root=str(repo)))


def _guard_config(repo: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((repo / GUARD_CONFIG).read_bytes())
    return loaded


def _settings(repo: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((repo / SETTINGS).read_text(encoding="utf-8"))
    return loaded


def _prompt_handlers(settings: dict[str, Any]) -> list[dict[str, Any]]:
    groups = settings["hooks"].get("UserPromptSubmit", [])
    return [handler for group in groups for handler in group["hooks"]]


def _assert_nothing_rendered(repo: Path) -> None:
    config, settings = _guard_config(repo), _settings(repo)
    assert not set(OVERLAY_IDS) & set(config["hooks"])
    assert config["network"] == {"mode": ""}
    assert "WebSearch" not in settings.get("permissions", {}).get("deny", [])
    assert "network" not in settings.get("sandbox", {})
    assert not any("onFailure" in handler for handler in _prompt_handlers(settings))


def test_engine_defaults_render_nothing_for_overlay_tier(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo)

    assert _sync_repo(repo, tmp_path) == 0

    _assert_nothing_rendered(repo)


def test_enable_list_cannot_activate_overlay_tier_hook(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    enable = ", ".join(f'"{hook_id}"' for hook_id in OVERLAY_IDS)
    repo = _repo(tmp_path, make_synthetic_repo, extra=f"{_HOOKS_ON}enable = [{enable}]\n")

    assert _sync_repo(repo, tmp_path) == 0

    _assert_nothing_rendered(repo)
    out = capsys.readouterr()
    assert "an overlay-tier mechanism; [hooks] cannot switch it on" in out.out + out.err


def test_fixture_overlay_activates_all_three_guards(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, regulated_overlay: str
) -> None:
    repo = _repo(tmp_path, make_synthetic_repo, overlay=regulated_overlay)

    assert _validate_repo(repo) == 0
    assert _sync_repo(repo, tmp_path) == 0

    config, settings = _guard_config(repo), _settings(repo)
    records = {hook_id: config["hooks"][hook_id] for hook_id in OVERLAY_IDS}
    assert {r["source_package"] for r in records.values()} == {regulated_overlay}
    assert records[NETWORK]["mandatory"] is True
    assert records[NETWORK]["handlers"]["pre_tool_use"]["config"]["mode"] == "enforce"
    assert config["network"] == {"mode": "enforce"}
    assert "WebSearch" in settings["permissions"]["deny"]
    domains = settings["sandbox"]["network"]["allowedDomains"]
    assert domains == [*OVERLAY_HOSTS, "litellm.bank.example"]
    assert "./data/raw" in settings["sandbox"]["filesystem"]["denyRead"]
    (strict,) = [h for h in _prompt_handlers(settings) if "--strict-launch" in h["command"]]
    assert strict["onFailure"] == "block"  # pii-prompt-guard's on_error: deny (OQ-18)


def test_disable_cannot_turn_off_mandatory_hook_h15(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    regulated_overlay: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    extra = f'{_HOOKS_ON}disable = ["{NETWORK}", "sensitive-data-read-guard"]\n'
    repo = _repo(tmp_path, make_synthetic_repo, overlay=regulated_overlay, extra=extra)

    assert _validate_repo(repo) == 1
    validated = capsys.readouterr().out
    assert _sync_repo(repo, tmp_path) == 1  # the validate gate: nothing is written

    message = (
        f"[hooks] disable: {NETWORK!r} is mandatory (overlay {regulated_overlay}) "
        "and cannot be disabled"
    )
    assert message in validated
    assert "'sensitive-data-read-guard' is mandatory" not in validated  # not mandatory
    assert not (repo / GUARD_CONFIG).exists()


def test_hooks_disabled_with_mandatory_overlay_is_validate_error(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    regulated_overlay: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    extra = "\n[hooks]\nenabled = false\n"
    repo = _repo(tmp_path, make_synthetic_repo, overlay=regulated_overlay, extra=extra)

    assert _validate_repo(repo) == 1

    assert (
        f"[hooks] enabled = false while overlay {regulated_overlay!r} ships mandatory hook "
        f"{NETWORK!r}; mandatory hooks cannot be switched off: set enabled = true"
    ) in capsys.readouterr().out


def test_consumer_allowed_hosts_ignored_for_mandatory_hook(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    regulated_overlay: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Relax keys and a weaker mode from the consumer never loosen the mandatory guard (§A.6)."""
    extra = (
        f'{_HOOKS_ON}\n[hooks.{NETWORK}]\nallowed_hosts = ["pypi.org"]\n'
        'webfetch_max_query_chars = 4096\n\n[guardrails.network]\nmode = "off"\n'
        'allowed_hosts = ["github.com"]\n\n[hooks.sensitive-data-read-guard]\n'
        'allow_globs = ["notebooks/**"]\n'
    )
    repo = _repo(tmp_path, make_synthetic_repo, overlay=regulated_overlay, extra=extra)

    assert _sync_repo(repo, tmp_path) == 0

    hooks = _guard_config(repo)["hooks"]
    network = hooks[NETWORK]["handlers"]["pre_tool_use"]["config"]
    assert network["allowed_hosts"] == OVERLAY_HOSTS
    assert (network["mode"], network["webfetch_max_query_chars"]) == ("enforce", 256)
    assert _settings(repo)["sandbox"]["network"]["allowedDomains"] == [
        *OVERLAY_HOSTS,
        "litellm.bank.example",
    ]
    data = hooks["sensitive-data-read-guard"]["handlers"]["pre_tool_use"]["config"]
    assert "notebooks/**" in data["allow_globs"]  # not mandatory: the consumer may relax it
    out = capsys.readouterr()
    assert f"[hooks.{NETWORK}] allowed_hosts is ignored for {NETWORK!r}" in out.out + out.err
