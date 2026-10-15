"""``playbook scan-sinks``: the deserialization guard's off-workstation twin (specs/prK-hook-pack.md §E.3).

Every row runs the real command in-process against a real repository built
under ``hermetic_git_env`` (through ``real_git``): a stateless ``SafeGit``
reads the staged blobs or the range, and the sink table is the one the guard's
``HOOK.md`` ships. Exit codes: 0 clean, 1 a new block sink, 2 a usage error.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.cli import main
from coding_agent_playbook.commands.scan_sinks import SinkChange, scan_changes, shipped_table

if TYPE_CHECKING:
    from collections.abc import Callable

LOADER: Final = "import pickle\n\n\ndef load(blob):\n    return pickle.loads(blob)\n"


class Repo:
    """A real repository on ``main``; ``commit`` writes files and commits, ``stage`` only adds."""

    def __init__(self, root: Path, git: Callable[..., str]) -> None:
        self.root = root
        self.git = git

    def stage(self, files: dict[str, str]) -> None:
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.git("add", "-A", cwd=self.root)

    def commit(self, message: str, files: dict[str, str]) -> None:
        self.stage(files)
        self.git("commit", "-q", "-m", message, cwd=self.root)

    def scan(self, *args: str) -> int:
        return main(["scan-sinks", *args, "--repo-root", str(self.root)])


@pytest.fixture
def repo(tmp_path: Path, real_git: Callable[..., str]) -> Repo:
    root = Path(os.path.realpath(tmp_path)) / "consumer"
    root.mkdir()
    real_git("init", "-q", "-b", "main", cwd=root)
    built = Repo(root, real_git)
    built.commit("init", {"src/app/model.py": LOADER, "README.md": "x\n"})
    return built


def test_staged_new_sink_exits_1(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.stage({"src/app/io.py": "import pickle as pk\nx = pk.loads(b)\n"})

    assert repo.scan("--staged") == 1

    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("src/app/io.py:2: pickle.loads: Load a data-only format instead")
    assert out[-1] == "scan-sinks staged: 1 blocking, 0 noted"


def test_range_counts_new_vs_base_only(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    edited = LOADER.replace("def load(blob):", "def load(blob: bytes) -> object:")
    repo.commit("annotate", {"src/app/model.py": edited + "\nM = torch.load(p)\n"})

    assert repo.scan("--range", "HEAD~1..HEAD", "--format", "json") == 0

    document = json.loads(capsys.readouterr().out)
    assert [(f["path"], f["call"], f["status"]) for f in document["findings"]] == [
        ("src/app/model.py", "torch.load", "warn")
    ]
    assert (document["blocking"], document["exit"]) == (0, 0)


def test_clean_range_exits_0(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.commit("docs", {"README.md": "y\n", "src/app/safe.py": "import json\nx = json.loads(s)\n"})

    assert repo.scan("--range", "HEAD~1..HEAD") == 0
    assert capsys.readouterr().out.strip() == "scan-sinks HEAD~1..HEAD: clean (0 noted)"


def test_notebook_cell_sink_is_found_without_a_line(repo: Repo) -> None:
    cells = [{"cell_type": "code", "source": "import numpy as np\nnp.load(f, allow_pickle=True)"}]
    notebook = json.dumps({"cells": cells, "nbformat": 4, "nbformat_minor": 5})

    [finding] = scan_changes([SinkChange("nb/a.ipynb", None, notebook)], shipped_table())

    assert (finding.text().split(": ")[0], finding.status) == ("nb/a.ipynb", "blocking")


def test_pragma_present_at_base_passes_a_new_one_is_a_note() -> None:
    pragma = "# playbook: trusted-artifact s3://models/v3"
    before = f"import pickle\n{pragma}\nM = None\n"
    after = f"import pickle\n{pragma}\nM = pickle.loads(b)\n"

    vouched = scan_changes([SinkChange("a.py", before, after)], shipped_table())
    fresh = scan_changes([SinkChange("a.py", "import pickle\n", after)], shipped_table())

    assert vouched == []
    assert [f.status for f in fresh] == ["new_pragma"]


def test_both_staged_and_range_is_a_usage_error(repo: Repo) -> None:
    with pytest.raises(SystemExit) as exc:
        repo.scan("--staged", "--range", "HEAD~1..HEAD")

    assert exc.value.code == 2


def test_bad_range_exits_2(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    assert repo.scan("--range", "HEAD") == 2
    assert "expected A..B or A...B" in capsys.readouterr().err
