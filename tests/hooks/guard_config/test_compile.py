"""``compile_guard_config``: the sync-level ``guard_config.json`` (specs/prK-lifecycle-hooks.md §C.0, §D.8).

Sync hands the writer a ``GuardConfigRequest`` holding only what sync owns; the
writer reads every other input from the repository itself (specs/prT-package-layout.md
9 AC.2.3), and a missing or broken file keeps its reader's default. The file is
committed and byte-compared by ``sync --check`` on every machine, so its bytes depend
only on the request and the repository: no absolute path, no ``sys.prefix``, no
``$HOME`` (§D.8.3). The envelope and the hook records are tested in ``test_envelope``,
the pack tables in ``test_pack_tables`` and ``test_tables_*``, and the runtime's read
of the written file in ``test_round_trip``.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from typing import TYPE_CHECKING, Any, Literal

import pytest

from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.config.files import CONFIG_FILENAME, CONFIG_LOCAL_FILENAME
from coding_agent_playbook.detector.facts import detect
from coding_agent_playbook.hook_runtime.config.schema import GUARD_CONFIG_REL
from coding_agent_playbook.hooks.guard_config.compile import (
    GuardConfigRequest,
    compile_guard_config,
    serialize_guard_config,
)
from coding_agent_playbook.hooks.guard_config.inputs import DetectInputs
from tests.hook_samples import resolved_hook
from tests.hooks.guard_config.compile_kit import (
    compiled_document,
    handler_config,
    request_for,
    two_hooks,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook


# --- the interface: what sync hands over, what comes back -----------------------------


def test_request_fields_are_only_what_sync_owns() -> None:
    """GC-D2: sync hands over what it computes; the writer reads every repo file itself."""
    assert {field.name for field in dataclasses.fields(GuardConfigRequest)} == {
        "repo_root",
        "hooks",
        "hooks_config",
        "guardrails",
        "engine_version",
        "generated",
        "protected",
        "detect",
        "prompts",
        "rules",
    }


def test_compiled_data_is_the_canonical_serialization(repo: Path) -> None:
    hooks = [resolved_hook("guard-y", config={"note": "café"})]

    result = compile_guard_config(request_for(repo, hooks))

    assert result.data == serialize_guard_config(result.document)
    assert b'"note":"caf\\u00e9"' in result.data
    assert result.data.isascii()
    assert result.data.endswith(b"}\n") and result.data.count(b"\n") == 1


def test_canonical_serialization_sorted_compact_ascii_newline() -> None:
    data = {"b": 1, "a": {"z": "é", "y": [1, 2]}}

    blob = serialize_guard_config(data)

    assert blob == b'{"a":{"y":[1,2],"z":"\\u00e9"},"b":1}\n'
    assert blob == (
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("ascii")


def test_check_mode_reads_the_real_repo_not_the_output_root(repo: Path, tmp_path: Path) -> None:
    """GC-D3: ``sync --check`` writes into an empty scratch dir, yet every repo input is read
    from ``repo_root``, so both output roots get the same bytes."""
    (repo / "ruff.toml").write_text('[lint]\nselect = ["I"]\n', encoding="utf-8")
    result = compile_guard_config(request_for(repo))
    scratch = tmp_path / "scratch"

    written = [result.write(out_root) for out_root in (repo, scratch)]

    assert written == [repo / GUARD_CONFIG_REL, scratch / GUARD_CONFIG_REL]
    assert written[0].read_bytes() == written[1].read_bytes() == result.data
    assert b'"project_select":["I"]' in result.data
    assert not (scratch / "ruff.toml").exists()


def test_compile_is_machine_independent(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hooks = two_hooks(tmp_path)
    datas: list[bytes] = []
    for prefix, home in (("/opt/venv-a", tmp_path / "home-a"), ("/srv/venv-b", tmp_path / "b")):
        monkeypatch.setattr(sys, "prefix", prefix)
        monkeypatch.setenv("HOME", str(home))
        datas.append(compile_guard_config(request_for(repo, hooks)).data)

    assert datas[0] == datas[1]
    text = datas[0].decode("ascii")
    assert str(tmp_path) not in text
    assert "/opt/" not in text and "/srv/" not in text
    assert '"protected":' in text and '"sentinel":' in text
    assert "site-packages" not in text


# --- the repo inputs the writer reads itself (GC-D2, GC-D5) ----------------------------


def test_compile_reads_the_project_ruff_selection(repo: Path) -> None:
    (repo / "ruff.toml").write_text('[lint]\nselect = ["I"]\n', encoding="utf-8")

    table = compiled_document(request_for(repo))["ruff"]

    assert table == {
        "default_select": False,
        "project_select": ["I"],
        "project_ignore": [],
        "safe_fix_select": ["I"],
        "safe_fix_ignore": [],
    }


@pytest.mark.parametrize(
    ("name", "text", "selection"),
    [
        (
            "pyproject.toml",
            '[tool.ruff.lint]\nselect = ["E", "I", "UP"]\nextend-select = ["B"]\n'
            'ignore = ["E501"]\nextend-ignore = ["UP007"]\n',
            (False, ["B", "E", "I", "UP"], ["E501", "UP007"]),
        ),
        ("pyproject.toml", '[tool.ruff]\nselect = ["F", "I"]\n', (False, ["F", "I"], [])),
        ("ruff.toml", '[lint]\nselect = ["ALL"]\nignore = ["D"]\n', (False, ["ALL"], ["D"])),
        ("ruff.toml", 'line-length = 100\n[lint]\nextend-select = ["I"]\n', (True, ["I"], [])),
        ("pyproject.toml", '[project]\nname = "x"\n', (True, [], [])),
    ],
    ids=["pyproject-lint", "pyproject-legacy", "all", "defaults+extend", "no-tool-ruff"],
)
def test_compile_reads_every_ruff_config_shape(
    repo: Path, name: str, text: str, selection: tuple[bool, list[str], list[str]]
) -> None:
    """``[lint]`` keys first, the deprecated top-level ones as a fallback; a pyproject
    without ``[tool.ruff]`` is no ruff config, so ruff's defaults stay implicit."""
    (repo / name).write_text(text, encoding="utf-8")

    table = compiled_document(request_for(repo))["ruff"]

    assert (table["default_select"], table["project_select"], table["project_ignore"]) == selection


def test_compile_reads_the_ruff_config_ruff_itself_would_read(repo: Path) -> None:
    """Ruff's precedence: ``.ruff.toml`` over ``ruff.toml`` over ``pyproject.toml``."""
    (repo / "pyproject.toml").write_text('[tool.ruff.lint]\nselect = ["E"]\n', "utf-8")
    (repo / "ruff.toml").write_text('[lint]\nselect = ["F"]\n', "utf-8")
    over_pyproject = compiled_document(request_for(repo))["ruff"]["project_select"]
    (repo / ".ruff.toml").write_text('[lint]\nselect = ["I"]\n', "utf-8")
    over_both = compiled_document(request_for(repo))["ruff"]["project_select"]

    assert (over_pyproject, over_both) == (["F"], ["I"])


@pytest.mark.parametrize(
    ("pyproject", "hints"),
    [
        (
            '[project]\nname = "x"\n\n[dependency-groups]\ndev = ["ruff>=0.6"]\n',
            {"install_hint": "uv sync --group dev", "cz_install_hint": ""},
        ),
        (
            '[project]\nname = "x"\n[project.optional-dependencies]\ndev = ["commitizen>=3"]\n',
            {"install_hint": "uv sync --extra dev", "cz_install_hint": "uv sync --extra dev"},
        ),
    ],
    ids=["dev-group-without-pytest", "commitizen-in-the-dev-extra"],
)
def test_compile_reads_toolchain_hints_from_pyproject(
    repo: Path, pyproject: str, hints: dict[str, str]
) -> None:
    """``uv.lock`` makes the detector report uv; the dev extra or group names the command."""
    (repo / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    hook = resolved_hook("toolchain-missing-hint", events=("post_tool_use",))
    request = dataclasses.replace(
        request_for(repo, [hook]), detect=DetectInputs(facts=detect(repo))
    )

    assert handler_config(compiled_document(request), "toolchain-missing-hint") == hints


_QUALITY_HOOK = "clean-code-metrics-nonregression"
_METRICS_TABLE = """\
[metrics.ruff_violations]
families = { quality = ["C901", "PLR1702"] }
config = { "lint.mccabe.max-complexity" = 10, "lint.pylint.max-nested-blocks" = 3 }
preview = true
"""


def test_compile_reads_the_quality_family_from_the_committed_metrics_table(repo: Path) -> None:
    """Team policy: the committed file only; ``.local.toml`` never applies to ``[metrics]``."""
    (repo / CONFIG_FILENAME).write_text(_METRICS_TABLE, encoding="utf-8")
    (repo / CONFIG_LOCAL_FILENAME).write_text(
        "[metrics.ruff_violations]\npreview = false\n", encoding="utf-8"
    )
    hook = resolved_hook(_QUALITY_HOOK, events=("post_tool_use",))

    document = compiled_document(request_for(repo, [hook]))

    assert handler_config(document, _QUALITY_HOOK) == {
        "lint_codes": {"warn": ["C901", "PLR1702"]},
        "ruff_config": ["lint.mccabe.max-complexity=10", "lint.pylint.max-nested-blocks=3"],
        "ruff_preview": True,
    }


_PRECOMMIT = """\
repos:
  - repo: local
    hooks:
      - id: playbook-sync-check
      - id: "coding-agent-playbook-sync"
      - id: ruff
#     - id: playbook-switched-off
"""


def test_compile_reads_precommit_ids_from_the_repo_config(repo: Path) -> None:
    """The runtime's own regex, so control-plane-guard and sync never disagree on the ids."""
    (repo / ".pre-commit-config.yaml").write_text(_PRECOMMIT, encoding="utf-8")

    table = compiled_document(request_for(repo))["precommit"]

    assert table == {"playbook_hook_ids": ["coding-agent-playbook-sync", "playbook-sync-check"]}


def _nudge_hook(config: dict[str, Any] | None = None) -> ResolvedHook:
    hook = resolved_hook("tests-with-source-nudge", events=("stop",), config=config)
    handler = dataclasses.replace(hook.handlers["stop"], name="tests_with_source_nudge")
    return dataclasses.replace(hook, handlers={"stop": handler})


def test_tests_nudge_roots_from_src_and_testpaths(repo: Path, tmp_path: Path) -> None:
    """``src`` (else ``.``) and pytest's ``testpaths`` (else ``tests``), read from the repo."""
    (repo / "src").mkdir()
    (repo / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["tests/unit", "integration/"]\n', "utf-8"
    )
    bare = tmp_path / "bare"
    bare.mkdir()

    hooks = compiled_document(request_for(repo, [_nudge_hook(), resolved_hook()]))
    consumer = compiled_document(request_for(repo, [_nudge_hook({"test_roots": ["checks"]})]))
    default = compiled_document(request_for(bare, [_nudge_hook()]))

    assert handler_config(hooks, "tests-with-source-nudge") == {
        "source_roots": ["src"],
        "test_roots": ["tests/unit", "integration"],
    }
    assert "source_roots" not in handler_config(hooks, "guard-x")
    nudge = handler_config(consumer, "tests-with-source-nudge")
    assert nudge["test_roots"] == ["checks"]  # the consumer's own roots win
    assert handler_config(default, "tests-with-source-nudge") == {
        "source_roots": ["."],
        "test_roots": ["tests"],
    }


def _member_rule(
    rule_id: str,
    skill: str | None,
    globs: list[str],
    *,
    scope: Literal["always", "scoped"] = "scoped",
) -> Rule:
    """A rendered rule with ``skill`` and ``globs``; the body is irrelevant to the table."""
    fm = RuleFrontmatter(
        id=rule_id, name=rule_id, description="d", scope=scope, globs=globs, skill=skill
    )
    return Rule(fm, "Body.\n", "Body.\n", False, None, "coding_agent_playbook")


def test_compile_derives_skill_globs_from_rendered_member_rules(repo: Path) -> None:
    """skill-nudge's table (specs/prS-skills-context.md 8.5.2): globs grouped by skill, rows
    sorted by skill id, each glob once in first-seen order; a rule without ``skill`` or
    ``globs`` adds no row."""
    rules = [
        _member_rule("fastapi-app-wiring", "python-tooling", ["**/api/**/*.py", "tests/**/*.py"]),
        _member_rule("python-typing", "python-coding", ["**/*.py"]),
        _member_rule("fastapi-error-boundaries", "python-tooling", ["**/*.py", "tests/**/*.py"]),
        _member_rule("python-error-handling", "python-coding", ["src/**/*.py", "**/*.py"]),
        _member_rule("python-house-style", None, [], scope="always"),
        _member_rule("project-context", None, ["**/*.py"], scope="always"),
        _member_rule("python-pure-core", "python-design", []),
    ]
    nudge = resolved_hook("skill-nudge", events=("post_tool_use",))
    request = dataclasses.replace(request_for(repo, [nudge]), rules=rules)

    config = handler_config(compiled_document(request), "skill-nudge")

    assert config["skills"] == [
        {"id": "python-coding", "globs": ["**/*.py", "src/**/*.py"]},
        {"id": "python-tooling", "globs": ["**/api/**/*.py", "tests/**/*.py", "**/*.py"]},
    ]


_DEFAULT_RUFF: dict[str, Any] = {
    "default_select": True,
    "project_select": [],
    "project_ignore": [],
    "safe_fix_select": [],
    "safe_fix_ignore": [],
}
_DEFAULT_QUALITY: dict[str, Any] = {
    "lint_codes": {"warn": ["C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915"]},
    "ruff_config": [],
    "ruff_preview": False,
}


def _quality(document: Mapping[str, Any]) -> dict[str, Any]:
    return handler_config(document, _QUALITY_HOOK)


def _ruff_table(document: Mapping[str, Any]) -> dict[str, Any]:
    return dict(document["ruff"])


_UNREADABLE: list[Any] = [
    ("pyproject.toml", b"[tool.ruff\n", _ruff_table, _DEFAULT_RUFF),
    ("pyproject.toml", b"\xff", _ruff_table, _DEFAULT_RUFF),
    (
        "pyproject.toml",
        b"[project\n",
        lambda doc: handler_config(doc, "toolchain-missing-hint"),
        {"install_hint": "uv sync", "cz_install_hint": ""},
    ),
    (
        "pyproject.toml",
        b"[tool.pytest.ini_options\n",
        lambda doc: handler_config(doc, "tests-with-source-nudge"),
        {"source_roots": ["."], "test_roots": ["tests"]},
    ),
    ("ruff.toml", b"[lint\n", _ruff_table, _DEFAULT_RUFF),
    (
        ".pre-commit-config.yaml",
        b"- id: playbook-sync-check\n" + b"#" * (1024 * 1024),
        lambda doc: doc["precommit"],
        {"playbook_hook_ids": []},
    ),
    (  # no committed config: a local [metrics] never applies
        CONFIG_LOCAL_FILENAME,
        b'[metrics.ruff_violations]\nfamilies = { quality = ["C901"] }\n',
        _quality,
        _DEFAULT_QUALITY,
    ),
    *(
        (CONFIG_FILENAME, committed, _quality, _DEFAULT_QUALITY)
        for committed in (
            b'[metrics]\nmode = "sideways"\n',
            b'metrics = "x"\n',
            b"[metrics]\nmode = \n",
            b"\xff",
            b'[metrics.ruff_violations]\nfamilies = { quality = ["nope"] }\n',
        )
    ),
]


@pytest.mark.parametrize(
    ("name", "content", "table_of", "default"),
    _UNREADABLE,
    ids=[
        "malformed-pyproject-ruff",
        "pyproject-not-utf8",
        "malformed-pyproject-toolchain",
        "malformed-pyproject-layout",
        "malformed-ruff-toml",
        "precommit-over-1-mib",
        "no-committed-config",
        "invalid-metrics-value",
        "metrics-not-a-table",
        "committed-not-toml",
        "committed-not-utf8",
        "unknown-quality-code",
    ],
)
def test_compile_keeps_defaults_for_unreadable_repo_inputs(
    repo: Path,
    name: str,
    content: bytes,
    table_of: Callable[[Mapping[str, Any]], Any],
    default: dict[str, Any],
) -> None:
    """GC-D5: a sync-time reader degrades rather than raises. ``[metrics]`` is read after
    the adapters wrote, so a bad value keeps the defaults where ``playbook metrics``
    exits 2 (spec B.14 question 2: a follow-up makes ``playbook validate`` refuse it)."""
    (repo / name).write_bytes(content)
    hooks = [
        resolved_hook("toolchain-missing-hint", events=("post_tool_use",)),
        resolved_hook(_QUALITY_HOOK, events=("post_tool_use",)),
        _nudge_hook(),
    ]
    request = dataclasses.replace(
        request_for(repo, hooks), detect=DetectInputs(facts={"package_manager": "uv"})
    )

    assert table_of(compiled_document(request)) == default
