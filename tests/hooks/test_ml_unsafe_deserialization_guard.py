"""ml-unsafe-deserialization-guard: new unsafe sinks never reach the disk (specs/prK-hook-pack.md §E.3).

An ML-detected fixture repository (``ml_stack`` has torch, so the linked rule
``ml-serialization-security`` and the hook are rendered) drives Write, Edit
and NotebookEdit payloads through ``playbook-hook simulate pre_tool_use``.
``FakeGit`` answers the ``HEAD`` blob the pragma check reads.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.guard_config import DetectInputs
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import Harness
from coding_agent_playbook.hook_runtime.handlers.deser import deser_sink_guard
from coding_agent_playbook.hook_runtime.registry import declaration_of
from tests.hook_runtime.fakes import FakeGit
from tests.hooks.pack_repo import engine_hook, engine_rules, resolve_engine_hooks

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hook_payloads import HookPayloadCase
    from tests.hooks.pack_repo import PackRepo

    type Payload = Callable[[str, str, str], HookPayloadCase]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "ml-unsafe-deserialization-guard"
ML_FACTS: Final[Mapping[str, Any]] = {"ml_stack": {"torch": ">=2.3"}}
MODEL: Final = "src/app/model.py"
EXISTING: Final = "import pickle\n\n\ndef load(blob):\n    return pickle.loads(blob)\n"
PRAGMA: Final = "# playbook: trusted-artifact s3://models/v3 (sha256 9f2c)"


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    pack_repo.write(MODEL, EXISTING)
    pack_repo.install_pack([HOOK_ID], rules=engine_rules(), detect=DetectInputs(facts=ML_FACTS))
    return pack_repo


def _run(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    tool: str,
    tool_input: dict[str, Any],
    *,
    git: FakeGit | None = None,
    state: Path | None = None,
) -> SimulateReport:
    payload = repo.tool_payload(tool, tool_input)
    return repo.simulate(payload, deps(git=git or FakeGit()), state=state)


def _write(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], rel: str, content: str, **kw: Any
) -> SimulateReport:
    return _run(repo, deps, "Write", {"file_path": str(repo.root / rel), "content": content}, **kw)


def _edit(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], old: str, new: str, **kw: Any
) -> SimulateReport:
    tool_input = {"file_path": str(repo.root / MODEL), "old_string": old, "new_string": new}
    return _run(repo, deps, "Edit", tool_input, **kw)


def _decision(report: SimulateReport) -> Decision:
    return report.trace.combined.decision


@pytest.mark.parametrize(
    ("harness", "case"),
    [("claude_code", "mudg_write_pickle_loads"), ("opencode", "mudg_write_pickle_loads")],
)
def test_pickle_loads_added_denied(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    hook_payload: Payload,
    harness: str,
    case: str,
) -> None:
    golden = hook_payload(harness, "pre_tool_use", case)

    report = repo.simulate(repo.relocate(golden), deps(git=FakeGit()), harness=Harness(harness))

    combined, expected = report.trace.combined, golden.expected["result"]
    assert (combined.decision.value, combined.reason) == (expected["decision"], expected["reason"])
    assert report.trace.wire == golden.wire()
    assert combined.reason.splitlines()[0] == (
        '"src/app/io.py:5" adds pickle.loads(...): loading untrusted data this way runs code.'
    )


def test_torch_load_weights_only_true_none(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    report = _write(
        repo, deps, "src/app/w.py", "import torch\nm = torch.load(p, weights_only=True)\n"
    )

    assert _decision(report) is Decision.NONE


def test_bare_torch_load_context_once(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    state = tmp_path / "state"
    text = "import torch\nm = torch.load(p)\n"

    first = _write(repo, deps, "src/app/w.py", text, state=state)
    second = _write(repo, deps, "src/app/w.py", text + "n = torch.load(q)\n", state=state)

    assert _decision(first) is Decision.CONTEXT
    assert first.trace.combined.context == (
        '"src/app/w.py:2" torch.load(...): Pass weights_only=True: the default depends on '
        "the installed torch version.",
    )
    assert _decision(second) is Decision.NONE  # once per pattern per file per session


def test_eval_context(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    report = _write(repo, deps, "src/app/calc.py", "def run(s):\n    return eval(s)\n")

    assert _decision(report) is Decision.CONTEXT
    assert "eval(...)" in report.trace.combined.context[0]


def test_unchanged_existing_pickle_none(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    report = _edit(repo, deps, "def load(blob):", "def load(blob: bytes) -> object:")

    assert _decision(report) is Decision.NONE


def test_replace_all_counts_every_new_copy(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    repo.write(MODEL, "import pickle\nA = read(a)\nB = read(b)\n")
    tool_input = {
        "file_path": str(repo.root / MODEL),
        "old_string": "read(",
        "new_string": "pickle.loads(",
        "replace_all": True,
    }

    report = _run(repo, deps, "Edit", tool_input)

    assert _decision(report) is Decision.DENY
    assert "(and 1 more)" in report.trace.combined.reason


def test_alias_pk_loads_denied(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    report = _write(repo, deps, "src/app/a.py", "import pickle as pk\nx = pk.loads(b)\n")

    assert _decision(report) is Decision.DENY
    assert "pickle.loads(...)" in report.trace.combined.reason


def test_new_trusted_artifact_pragma_asks_head_pragma_none(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    committed = f"import pickle\n{PRAGMA}\nMODEL = None\n"
    repo.write(MODEL, committed)
    at_head = FakeGit(head_blobs={MODEL: committed.encode()})
    fresh = FakeGit(head_blobs={MODEL: b"import pickle\nMODEL = None\n"})

    trusted = _edit(repo, deps, "MODEL = None", "MODEL = pickle.loads(blob)", git=at_head)
    self_vouched = _edit(repo, deps, "MODEL = None", "MODEL = pickle.loads(blob)", git=fresh)

    assert _decision(trusted) is Decision.NONE
    assert _decision(self_vouched) is Decision.ASK
    assert self_vouched.trace.combined.reason.splitlines() == [
        '"src/app/model.py:3" adds pickle.loads(...) under a new trusted-artifact comment.',
        "Confirm the artifact's provenance: a comment written in this session cannot vouch for it.",
    ]


def _notebook(*cells: dict[str, Any]) -> str:
    return json.dumps({"cells": list(cells), "metadata": {}, "nbformat": 4, "nbformat_minor": 5})


def test_notebook_cell_np_load_allow_pickle_denied(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    rel = "nb/explore.ipynb"
    repo.write(
        rel,
        _notebook(
            {"id": "c0", "cell_type": "code", "source": ["import numpy as np\n"], "outputs": []},
            {"id": "c1", "cell_type": "code", "source": "x = 1", "outputs": []},
        ),
    )
    edit = {"notebook_path": str(repo.root / rel), "cell_id": "c1", "new_source": ""}

    denied = _run(
        repo, deps, "NotebookEdit", {**edit, "new_source": "a = np.load(f, allow_pickle=True)"}
    )
    safe = _run(
        repo, deps, "NotebookEdit", {**edit, "new_source": "a = np.load(f, allow_pickle=False)"}
    )

    assert _decision(denied) is Decision.DENY
    assert denied.trace.combined.reason.startswith('"nb/explore.ipynb" adds numpy.load(...)')
    assert _decision(safe) is Decision.NONE


def test_eval_task_setup_path_inactive(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    rel = "pkg/eval_tasks/find-injected-vuln-x/setup/app/loader.py"

    report = _write(repo, deps, rel, "import pickle\nx = pickle.loads(b)\n")

    assert _decision(report) is Decision.NONE


def test_unparseable_post_image_uses_regex_fallback(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    report = _write(repo, deps, "src/app/b.py", "import pickle\ndef f(:\n    pickle.loads(b)\n")

    assert _decision(report) is Decision.DENY
    assert report.trace.combined.reason.startswith('"src/app/b.py:3" adds pickle.loads(...)')


def test_edit_that_cannot_be_simulated_judges_its_fragments(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    """An ``old_string`` no longer in the file: the tool will fail, but its text is still judged."""
    added = _edit(repo, deps, "not in the file", "data = pickle.loads(raw)")
    kept = _edit(repo, deps, "return pickle.loads(blob)  # stale", "return pickle.loads(blob)")

    assert _decision(added) is Decision.DENY
    assert _decision(kept) is Decision.NONE  # the same sink on both sides: nothing new


def test_apply_patch_added_lines_are_judged(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    patch = (
        "*** Begin Patch\n*** Add File: src/app/new.py\n+import pickle\n"
        "+x = pickle.loads(b)\n*** End Patch\n"
    )
    payload = repo.tool_payload("apply_patch", {"patchText": patch, "patch_text": patch})

    report = repo.simulate(payload, deps(git=FakeGit()), harness=Harness.OPENCODE)

    assert _decision(report) is Decision.DENY
    assert "pickle.loads(...)" in report.trace.combined.reason


def test_notebook_write_judges_its_code_cells(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    cells: list[dict[str, Any]] = [
        {"cell_type": "markdown", "source": "pickle.loads(x) in prose is not code"},
        {"cell_type": "code", "source": ["import joblib\n", "m = joblib.load(p)"]},
    ]

    report = _write(repo, deps, "nb/train.ipynb", _notebook(*cells))

    assert _decision(report) is Decision.DENY
    assert report.trace.combined.reason.startswith('"nb/train.ipynb" adds joblib.load(...)')


def test_non_ml_repo_not_rendered(tmp_path: Path) -> None:
    rules = engine_rules()

    plain = resolve_engine_hooks([HOOK_ID], tmp_path, rules=rules, facts={})
    [ml] = resolve_engine_hooks([HOOK_ID], tmp_path, rules=rules, facts=ML_FACTS)

    assert plain == []
    config = ml.handlers["pre_tool_use"].config
    assert {"pickle.loads", "torch.load", "*"} <= {row["call"] for row in config["block"]}
    assert ml.matcher["pre_tool_use"].paths == ["**/*.py", "**/*.ipynb"]


def test_shipped_hook_matches_its_pack_row() -> None:
    fm = engine_hook(HOOK_ID).frontmatter
    declaration = declaration_of(deser_sink_guard)
    assert fm.handler is not None and declaration is not None

    assert (fm.tier, tuple(fm.events), tuple(fm.decisions), fm.on_error) == (
        "default",
        ("pre_tool_use",),
        ("deny", "ask", "context", "none"),
        "ask",
    )
    assert fm.linked_rule == "ml-serialization-security"
    assert fm.handler.builtin == declaration.name
    assert set(fm.handler.config) <= set(declaration.config_schema)
