"""The ``domino_project`` and ``playbook_layer`` facts (prU D63, D70, D78(2)).

Tested at two seams: ``detect()`` (what the detector reports for a repo) and
``evaluate_predicate`` (whether a ``domino_project: true`` gate, the one every
Domino skill's rules carry, holds for those facts).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from coding_agent_playbook.config.files import CONFIG_FILENAME
from coding_agent_playbook.detector.bounded_read import DETECTOR_INPUT_MAX_BYTES
from coding_agent_playbook.detector.facts import detect
from coding_agent_playbook.detector.platform_facts import committed_platforms, has_playbook_layer
from coding_agent_playbook.detector.predicate import evaluate_predicate
from coding_agent_playbook.detector.requirements_files import (
    REQUIREMENTS_MAX_BYTES,
    root_requirement_names,
)
from tests._budget_probe import write_authoring_probe, write_domino_probe, write_reference_probe

pytestmark = pytest.mark.catalog

_DOMINO_GATE = {"domino_project": True}
_ENGINE_REPO = Path(__file__).resolve().parents[2]
_OVERLAY_PYPROJECT = """\
[project]
name = "acme-rules"
dependencies = ["coding-agent-playbook>=0.21"]
"""


def _write(repo: Path, rel: str, text: str) -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def test_domino_probe_turns_the_domino_gate_on(tmp_path: Path) -> None:
    write_domino_probe(tmp_path)

    facts = detect(tmp_path)

    assert facts["domino_project"] is True
    assert evaluate_predicate(_DOMINO_GATE, facts)


def test_standard_probe_leaves_the_domino_gate_off(tmp_path: Path) -> None:
    write_reference_probe(tmp_path)

    facts = detect(tmp_path)

    assert facts["domino_project"] is False
    assert not evaluate_predicate(_DOMINO_GATE, facts)


@pytest.mark.parametrize("marker", [".dominoignore", ".dominoresults", "dominostats.json"])
def test_each_reliable_domino_file_marker_counts_alone(tmp_path: Path, marker: str) -> None:
    (tmp_path / marker).write_text("", encoding="utf-8")

    assert detect(tmp_path)["domino_project"] is True


@pytest.mark.parametrize("dependency", ["dominodatalab", "DominoDataLab_Data"])
def test_a_domino_dependency_counts_alone(tmp_path: Path, dependency: str) -> None:
    _write(
        tmp_path, "pyproject.toml", f'[project]\nname = "x"\ndependencies = ["{dependency}>=1"]\n'
    )

    assert detect(tmp_path)["domino_project"] is True


def test_app_sh_and_mnt_paths_alone_do_not_make_a_domino_project(tmp_path: Path) -> None:
    _write(tmp_path, "app.sh", "#!/bin/sh\nstreamlit run app.py --server.port 8888\n")
    _write(tmp_path, "main.py", 'DATA = "/mnt/data/train.csv"\n')

    assert detect(tmp_path)["domino_project"] is False


def test_platforms_domino_turns_the_gate_on_in_a_marker_free_repo(tmp_path: Path) -> None:
    write_reference_probe(tmp_path)
    _write(tmp_path, CONFIG_FILENAME, 'schema_version = 1\nplatforms = ["domino"]\n')

    assert evaluate_predicate(_DOMINO_GATE, detect(tmp_path))


@pytest.mark.parametrize(
    "config",
    [
        "schema_version = 1\n",
        'platforms = "domino"\n',
        'platforms = ["aws"]\n',
        "platforms = [\n",  # malformed TOML: the detector never raises
        '[user_choices]\nplatforms = ["domino"]\n',  # nested, so not the top-level key
    ],
)
def test_the_platforms_key_counts_only_as_a_top_level_list_naming_domino(
    tmp_path: Path, config: str
) -> None:
    _write(tmp_path, CONFIG_FILENAME, config)

    assert detect(tmp_path)["domino_project"] is False


def test_platforms_in_the_local_config_does_not_count(tmp_path: Path) -> None:
    _write(tmp_path, ".coding-agent-playbook.local.toml", 'platforms = ["domino"]\n')

    assert detect(tmp_path)["domino_project"] is False


def test_root_requirements_names_feed_dependencies_frameworks_and_domino(tmp_path: Path) -> None:
    _write(tmp_path, "requirements.txt", "dominodatalab==1.4  # client\nFlask>=3\n")
    _write(tmp_path, "requirements-dev.txt", "-r requirements.txt\npytest\n")

    facts = detect(tmp_path)

    assert facts["dependencies"] == {"dominodatalab": "", "flask": "", "pytest": ""}
    assert facts["frameworks"] == {"flask": "", "pytest": ""}
    assert facts["domino_project"] is True
    assert evaluate_predicate({"has_framework": ["flask"]}, facts)


def test_a_pyproject_constraint_wins_over_a_requirements_entry(tmp_path: Path) -> None:
    _write(tmp_path, "pyproject.toml", '[project]\nname = "x"\ndependencies = ["flask>=3"]\n')
    _write(tmp_path, "requirements.txt", "flask\nhttpx\n")

    facts = detect(tmp_path)

    assert facts["dependencies"] == {"flask": ">=3", "httpx": ""}


def test_nested_requirements_files_are_not_read(tmp_path: Path) -> None:
    _write(tmp_path, "docs/requirements.txt", "dominodatalab\n")

    facts = detect(tmp_path)

    assert "dependencies" not in facts
    assert facts["domino_project"] is False


def test_authoring_probe_turns_the_playbook_layer_gate_on_and_leaves_domino_off(
    tmp_path: Path,
) -> None:
    write_authoring_probe(tmp_path)

    facts = detect(tmp_path)

    assert facts["playbook_layer"] is True
    assert facts["domino_project"] is False


def test_playbook_layer_is_true_in_this_engine_repo() -> None:
    assert has_playbook_layer(_ENGINE_REPO, frozenset()) is True


def test_playbook_layer_is_true_with_an_empty_playbook_directory(tmp_path: Path) -> None:
    write_reference_probe(tmp_path)
    (tmp_path / "playbook").mkdir()

    facts = detect(tmp_path)

    assert facts["playbook_layer"] is True
    assert evaluate_predicate({"playbook_layer": True}, facts)


@pytest.mark.parametrize("package_dir", ["src/acme_rules", "acme_rules"])
def test_playbook_layer_is_true_in_an_overlay_package(tmp_path: Path, package_dir: str) -> None:
    _write(tmp_path, "pyproject.toml", _OVERLAY_PYPROJECT)
    _write(tmp_path, f"{package_dir}/resources/rules/acme-naming.md", "---\nid: acme-naming\n---\n")

    assert detect(tmp_path)["playbook_layer"] is True


def test_playbook_layer_needs_the_engine_dependency_for_an_overlay(tmp_path: Path) -> None:
    _write(tmp_path, "pyproject.toml", '[project]\nname = "acme"\ndependencies = []\n')
    _write(tmp_path, "src/acme/resources/rules/x.md", "")

    assert detect(tmp_path)["playbook_layer"] is False


def test_playbook_layer_is_false_in_the_standard_probe(tmp_path: Path) -> None:
    write_reference_probe(tmp_path)

    facts = detect(tmp_path)

    assert facts["playbook_layer"] is False
    assert not evaluate_predicate({"playbook_layer": True}, facts)


def _run_vcs(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, timeout=30)


def test_an_untracked_dominostats_json_in_a_git_repo_does_not_count(tmp_path: Path) -> None:
    """A Domino run writes dominostats.json; D63 counts only a committed one."""
    _run_vcs(tmp_path, "init", "-q")
    _write(tmp_path, "dominostats.json", "{}\n")

    assert detect(tmp_path)["domino_project"] is False


def test_a_tracked_dominostats_json_in_a_git_repo_counts(tmp_path: Path) -> None:
    _run_vcs(tmp_path, "init", "-q")
    _write(tmp_path, "dominostats.json", "{}\n")
    _run_vcs(tmp_path, "add", "dominostats.json")

    assert detect(tmp_path)["domino_project"] is True


def test_an_oversized_committed_config_yields_no_platforms(tmp_path: Path) -> None:
    padding = "#\n" * (DETECTOR_INPUT_MAX_BYTES // 2)
    _write(tmp_path, CONFIG_FILENAME, 'platforms = ["domino"]\n' + padding)

    assert committed_platforms(tmp_path) == frozenset()


def test_a_domino_dependency_in_an_optional_group_counts(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        '[project]\nname = "x"\n[project.optional-dependencies]\ndomino = ["dominodatalab"]\n',
    )

    assert detect(tmp_path)["domino_project"] is True


@pytest.mark.parametrize("unusable", ["oversized", "not-utf8", "directory"])
def test_an_unusable_root_requirements_file_contributes_nothing(
    tmp_path: Path, unusable: str
) -> None:
    target = tmp_path / "requirements-x.txt"
    if unusable == "oversized":
        target.write_text("dominodatalab\n" + "#\n" * REQUIREMENTS_MAX_BYTES, encoding="utf-8")
    elif unusable == "not-utf8":
        target.write_bytes(b"dominodatalab\n# caf\xe9\n")
    else:
        target.mkdir()
    _write(tmp_path, "requirements.txt", "flask\n")

    assert root_requirement_names(tmp_path) == frozenset({"flask"})
