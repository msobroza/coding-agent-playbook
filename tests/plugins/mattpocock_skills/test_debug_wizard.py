"""T07: diagnosing-bugs and wizard, their texts and their two Python scripts.

specs/prT-mattpocock-skills.md A.T07. The shared gate (``test_gates.py``) already
runs G19 on the scripts; this file pins every new text of A.T07 as an exact
substring, the absence of each replaced upstream text, and the scripts'
behaviour. Section 7.7 forbids importing a script in the pytest process (that
writes ``scripts/__pycache__/`` into the catalog), so every behaviour test runs
it in a subprocess started with ``sys.executable -B``; static checks parse the
source with ``ast`` and import nothing.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shlex
import stat
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest

from tests.plugins.mattpocock_skills._expectations import (
    PLUGIN_ROOT,
    SKILLS_ROOT,
    skill_files,
    split_skill,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_DIAGNOSING = SKILLS_ROOT / "diagnosing-bugs"
_WIZARD = SKILLS_ROOT / "wizard"
_HITL_SCRIPT = _DIAGNOSING / "scripts" / "hitl_loop_template.py"
_WIZARD_SCRIPT = _WIZARD / "scripts" / "wizard_template.py"
_TIMEOUT_S = 60
#: Upstream's comment rules (template.sh L11, L13, L182, L185, L202): 76 characters.
_RULE = "# " + "─" * 74
_EXAMPLE_RULE = "# ── Example stage: replace with your real steps " + "─" * 27
_SCREEN_CLEAR = "\033[2J\033[3J\033[H"

# --- the driver (A.T07.1), shared by both scripts --------------------------------

#: Run in a child ``python -B -c``: reads a JSON scenario on stdin, swaps in named
#: fakes for the terminal, getpass, webbrowser and (optionally) ``os.replace``, loads
#: the script without running its ``__main__`` block, runs the scenario's calls and
#: prints one JSON line to the real stdout.
_SCRIPT_DRIVER = r'''
import contextlib
import getpass
import importlib.util
import io
import json
import os
import sys
import webbrowser

scenario = json.loads(sys.stdin.read())


class FakeTerminalStdin(io.StringIO):
    """Stdin over the scenario's lines, a terminal unless told otherwise."""

    def __init__(self, lines, tty, interrupt_on_read):
        super().__init__("".join(line + "\n" for line in lines))
        self.tty = tty
        self.interrupt_on_read = interrupt_on_read
        self.reads = 0

    def isatty(self):
        return self.tty

    def readline(self, size=-1):
        self.reads += 1
        if self.reads == self.interrupt_on_read:
            raise KeyboardInterrupt
        return super().readline(size)


class FakeTerminalStdout(io.StringIO):
    """Captured stdout that may claim to be a terminal."""

    def __init__(self, tty):
        super().__init__()
        self.tty = tty

    def isatty(self):
        return self.tty


class FakeGetpass:
    """Records each prompt and returns the queued answers; end of file once they run out."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.prompts = []

    def __call__(self, prompt="Password: ", stream=None):
        self.prompts.append(prompt)
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)


class FakeBrowserOpen:
    """Records each [url, new] and opens, fails or raises as the scenario says."""

    def __init__(self, mode):
        self.mode = mode
        self.calls = []

    def __call__(self, url, new=0, autoraise=True):
        self.calls.append([url, new])
        if self.mode == "raises":
            raise webbrowser.Error("no runnable browser")
        return self.mode == "opens"


def failing_replace(src, dst, **kwargs):
    raise OSError("replace failed")


sys.stdin = FakeTerminalStdin(
    scenario.get("stdin", []), scenario.get("stdin_tty", True), scenario.get("interrupt_on_read")
)
stdout = FakeTerminalStdout(scenario.get("stdout_tty", False))
stderr = io.StringIO()
fake_getpass = FakeGetpass(scenario.get("getpass", []))
fake_open = FakeBrowserOpen(scenario.get("browser", "opens"))
getpass.getpass = fake_getpass
webbrowser.open = fake_open
if scenario.get("fail_replace"):
    os.replace = failing_replace

results = []
with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
    spec = importlib.util.spec_from_file_location("script_under_test", scenario["script"])
    module = importlib.util.module_from_spec(spec)
    sys.modules["script_under_test"] = module
    spec.loader.exec_module(module)
    for name, value in scenario.get("set", {}).items():
        setattr(module, name, value)
    for name, *args in scenario["calls"]:
        try:
            if name == "__run__":
                if hasattr(module, "run_wizard"):
                    value = module.run_wizard(module.wizard_stages)
                else:
                    value = module.run_hitl_loop(module.hitl_steps)
            elif name == "__get__":
                value = getattr(module, args[0])
            else:
                value = getattr(module, name)(*args)
            results.append({"value": value, "error": None})
        except BaseException as exc:
            results.append({"value": None, "error": [type(exc).__name__, str(exc)]})

names = (
    "CAPTURED", "WRITTEN_ENV", "WRITTEN_SECRET", "WRITTEN_VAR", "SKIPPED", "ENV_FILE",
    "TOTAL_STAGES", "_STAGE_INDEX",
)
report = {
    "results": results,
    "stdout": stdout.getvalue(),
    "stderr": stderr.getvalue(),
    "getpass_prompts": fake_getpass.prompts,
    "browser_calls": fake_open.calls,
    "state": {name: getattr(module, name) for name in names if hasattr(module, name)},
}
print(json.dumps(report), file=sys.__stdout__)
'''


def _child_env(extra: dict[str, str]) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in {"ENV_FILE", "BROWSER"}}
    return {**env, "TERM": "dumb", **extra}


def run_script_scenario(script: Path, scenario: dict[str, object], cwd: Path) -> dict[str, Any]:
    """Run ``scenario`` against ``script`` through the driver; return its JSON report.

    Example: ``run_script_scenario(_HITL_SCRIPT, {"stdin": [], "calls": [["__run__"]]}, tmp_path)``.
    """
    scenario["script"] = str(script)
    extra = scenario.get("env", {})
    assert isinstance(extra, dict)
    proc = subprocess.run(
        [sys.executable, "-B", "-c", _SCRIPT_DRIVER],
        input=json.dumps(scenario),
        cwd=cwd,
        env=_child_env(extra),
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report: dict[str, Any] = json.loads(proc.stdout.strip().split("\n")[-1])
    return report


def _run_without_a_terminal(script: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    """The real script, as an agent shell runs it: stdin is not a terminal."""
    return subprocess.run(
        [sys.executable, "-B", str(script)],
        stdin=subprocess.DEVNULL,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
        check=False,
    )


def _value(report: dict[str, Any], index: int = 0) -> Any:
    result = report["results"][index]
    assert result["error"] is None, result["error"]
    return result["value"]


def _error(report: dict[str, Any], index: int = 0) -> list[str]:
    error: list[str] | None = report["results"][index]["error"]
    assert error is not None, f"expected an error, got {report['results'][index]['value']!r}"
    return error


def _module_tree(script: Path) -> ast.Module:
    return ast.parse(script.read_text(encoding="utf-8"), filename=str(script))


def _top_level_defs(tree: ast.Module) -> dict[str, int]:
    return {node.name: node.lineno for node in tree.body if isinstance(node, ast.FunctionDef)}


def _is_main_block(node: ast.stmt) -> bool:
    return isinstance(node, ast.If) and ast.unparse(node.test) == "__name__ == '__main__'"


def _docstring(tree: ast.Module, name: str) -> str:
    """The top-level function's docstring, with its line breaks collapsed to spaces."""
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return " ".join((ast.get_docstring(node) or "").split())


# --- diagnosing-bugs: SKILL.md (A.T07.1 changes 1-7) ------------------------------

_DIAGNOSING_DESCRIPTION = (
    "Diagnosis loop for hard bugs and performance regressions. Use when the user says "
    '"diagnose"/"debug this", or reports something broken/throwing/failing/slow.'
)
_DIAGNOSING_NEW_TEXTS = (
    "When exploring the codebase, read `GLOSSARY.md` (or `CONTEXT.md` if the repo already has "
    "one) (if it exists) to get a clear mental model of the relevant modules, and check ADRs in "
    "the area you're touching.",
    "2. **HTTP script** against a running dev server.",
    "4. **Headless browser script** (Playwright) that drives the UI and asserts on "
    "DOM/console/network.",
    "10. **HITL Python script.** Last resort. If a human must click, drive _them_ with "
    "`scripts/hitl_loop_template.py` so the loop is still structured. Captured output feeds "
    "back to you.",
    "you can name **one command** (a script path, a test invocation) that you have **already "
    "run at least once**",
    "- [ ] **Agent-runnable**: you can run it unattended; a human in the loop only via "
    "`scripts/hitl_loop_template.py`.",
)
_DIAGNOSING_REPLACED = (
    "Curl / HTTP script",
    "Playwright / Puppeteer",
    ", a curl)",
    "HITL bash script",
    "hitl-loop.template.sh",
)


def test_diagnosing_bugs_frontmatter_adds_only_the_id() -> None:
    text = (_DIAGNOSING / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith(
        f"---\nid: diagnosing-bugs\nname: diagnosing-bugs\ndescription: {_DIAGNOSING_DESCRIPTION}\n---\n"
    )
    frontmatter, _ = split_skill("diagnosing-bugs")
    assert frontmatter == {
        "id": "diagnosing-bugs",
        "name": "diagnosing-bugs",
        "description": _DIAGNOSING_DESCRIPTION,
    }


def test_diagnosing_bugs_skill_text() -> None:
    text = (_DIAGNOSING / "SKILL.md").read_text(encoding="utf-8")
    assert [t for t in _DIAGNOSING_NEW_TEXTS if t not in text] == []
    assert [t for t in _DIAGNOSING_REPLACED if t in text] == []
    assert text.count("`scripts/hitl_loop_template.py`") == 2
    assert len(text.split("\n")) == 140, "139 lines plus the final newline (A.T07.1 Files)"
    leaks = [
        p.name for p in skill_files("diagnosing-bugs") if b"hitl-loop.template.sh" in p.read_bytes()
    ]
    assert leaks == []


def test_diagnosing_bugs_skill_dir_holds_exactly_its_three_files() -> None:
    names = sorted(p.relative_to(_DIAGNOSING).as_posix() for p in skill_files("diagnosing-bugs"))
    assert names == ["SKILL.md", "references/LICENSE", "scripts/hitl_loop_template.py"]


# --- diagnosing-bugs: the HITL loop script (A.T07.1 changes 8-13) ------------------

_HITL_DOCSTRING_LINES = (
    "Human-in-the-loop reproduction loop.",
    "Copy this file, edit the steps below, and run it.",
    "The agent runs the script; the user follows prompts in their terminal.",
    "Usage:",
    "  python3 hitl_loop_template.py",
    "Two helpers:",
    '  step("<instruction>")          → show instruction, wait for Enter',
    '  capture("VAR", "<question>")   → show question, store the answer under VAR',
    "At the end, captured values are printed as KEY=VALUE for the agent to parse.",
    "`capture` prints its value back to the terminal, where the agent reads it,",
    "so capture observations, and leave signing in to the user as a `step`.",
)
_HITL_MARKERS = (
    "# --- edit below ---------------------------------------------------------",
    "# --- edit above ---------------------------------------------------------",
)
_HITL_EXAMPLE_CALLS = (
    '    step("Open the app at its local dev server address and sign in.")\n',
    '    capture("ERRORED", "Click the \'Export\' button. Did it throw an error? (y/n)")\n',
    '    capture("ERROR_MSG", "Paste the error message (or \'none\'):")\n',
)
_HITL_FIRST_STEP = "\n>>> Open the app at its local dev server address and sign in.\n"


def _hitl_no_terminal_message(script: Path) -> str:
    return (
        "This HITL loop needs a human at an interactive terminal, and stdin here is not one "
        "(or it was closed).\n"
        "Ask the user to run it in their own terminal, follow the prompts, and paste back the "
        '"--- Captured ---" block:\n'
        f"    python3 {shlex.quote(str(script.resolve()))}\n"
    )


def _hitl(cwd: Path, **scenario: object) -> dict[str, Any]:
    return run_script_scenario(_HITL_SCRIPT, dict(scenario), cwd)


def test_hitl_template_keeps_matt_text() -> None:
    source = _HITL_SCRIPT.read_text(encoding="utf-8")
    tree = _module_tree(_HITL_SCRIPT)
    docstring = ast.get_docstring(tree, clean=False) or ""
    assert source.startswith('#!/usr/bin/env python3\n"""Human-in-the-loop reproduction loop.\n')
    assert [line for line in _HITL_DOCSTRING_LINES if line not in docstring.split("\n")] == []
    assert [m for m in _HITL_MARKERS if source.count(f"    {m}\n") != 1] == []
    assert [c for c in _HITL_EXAMPLE_CALLS if c not in source] == []
    assert "localhost" not in source
    for upstream in ("bash", "read response into VAR", "set -euo pipefail", "printf"):
        assert upstream not in source, upstream
    defs = _top_level_defs(tree)
    assert {"step", "capture", "run_hitl_loop", "hitl_steps"} <= set(defs)
    assert _docstring(tree, "hitl_steps") == (
        "The steps the human takes, in order: one step() or capture() call each."
    )
    assert "# capture() stores each answer here, in capture order.\nCAPTURED" in source
    assert _is_main_block(tree.body[-1])
    assert source.endswith(
        'if __name__ == "__main__":\n    raise SystemExit(run_hitl_loop(hitl_steps))\n'
    )


def test_hitl_without_a_terminal_exits_2_and_asks_for_the_users_terminal(tmp_path: Path) -> None:
    proc = _run_without_a_terminal(_HITL_SCRIPT, tmp_path)
    assert proc.returncode == 2
    assert proc.stdout == "", "no step shown and no Captured block"
    assert proc.stderr == _hitl_no_terminal_message(_HITL_SCRIPT)
    assert "Traceback" not in proc.stderr


def test_hitl_run_prints_every_capture_in_order(tmp_path: Path) -> None:
    report = _hitl(tmp_path, stdin=["", "y", "TypeError: x is undefined"], calls=[["__run__"]])
    assert _value(report) == 0
    assert report["stdout"] == (
        f"{_HITL_FIRST_STEP}"
        "\n>>> Click the 'Export' button. Did it throw an error? (y/n)\n"
        "\n>>> Paste the error message (or 'none'):\n"
        "\n--- Captured ---\nERRORED=y\nERROR_MSG=TypeError: x is undefined\n"
    )
    assert report["stderr"] == "    [Enter when done]     >     > "


def test_hitl_trims_answers_like_read(tmp_path: Path) -> None:
    report = _hitl(tmp_path, stdin=["", "  y \t", "none"], calls=[["__run__"]])
    assert _value(report) == 0
    assert "\n--- Captured ---\nERRORED=y\nERROR_MSG=none\n" in report["stdout"]


def test_hitl_eof_mid_loop_exits_2_without_a_captured_block(tmp_path: Path) -> None:
    report = _hitl(tmp_path, stdin=[""], calls=[["__run__"]])
    assert _value(report) == 2
    assert report["stderr"].endswith(_hitl_no_terminal_message(_HITL_SCRIPT))
    assert "--- Captured ---" not in report["stdout"]


def test_hitl_ctrl_c_exits_130_quietly(tmp_path: Path) -> None:
    report = _hitl(tmp_path, stdin=["", "y", "z"], interrupt_on_read=1, calls=[["__run__"]])
    assert _value(report) == 130
    assert report["stdout"] == f"{_HITL_FIRST_STEP}\n"
    assert "Traceback" not in report["stderr"]


def test_hitl_capture_rejects_a_name_that_is_not_an_identifier(tmp_path: Path) -> None:
    report = _hitl(tmp_path, stdin=["x"], calls=[["capture", "bad name", "q"]])
    kind, message = _error(report)
    assert kind == "ValueError"
    assert "'bad name'" in message
    assert report["stdout"] == ""


def test_hitl_repeated_capture_name_keeps_its_place_and_last_value(tmp_path: Path) -> None:
    calls = [["capture", "A", "q"], ["capture", "B", "q"], ["capture", "A", "q"]]
    report = _hitl(tmp_path, stdin=["1", "2", "3"], calls=[*calls, ["_print_captured"]])
    assert [r["value"] for r in report["results"]] == ["1", "2", "3", None]
    assert report["stdout"].endswith("--- Captured ---\nA=3\nB=2\n")
    assert report["state"]["CAPTURED"] == {"A": "3", "B": "2"}


# --- wizard: SKILL.md (A.T07.2 changes 1-11) --------------------------------------

_WIZARD_DESCRIPTION = (
    "Generate an interactive Python wizard that walks a human through steps only they can "
    "perform. Use when provisioning infrastructure, setting up credentials or CI secrets, "
    "walking an unfamiliar third-party dashboard, or running a one-off migration or cutover. "
    "Don't invoke this for steps the agent can perform itself."
)
_WIZARD_NEW_TEXTS = (
    "Generate an interactive Python wizard",
    "A **wizard** is a Python script that walks a human, step by step, through a manual "
    "procedure that's tedious to do by hand and tedious to re-explain to an AI every time. It "
    "opens each URL, says exactly what to click and copy, captures the values, writes them where "
    "they belong (`.env`, or GitHub secrets it walks the human through setting), confirms at "
    "every stage, and shows how many stages are left. It might configure third-party services, "
    "run a one-off migration, or move the project from one state to another.",
    "The delightful UX is already solved by [wizard_template.py](scripts/wizard_template.py): "
    "stage-by-stage progress, confirmation gates, cross-platform URL opening (Python's "
    "`webbrowser`, printing the URL when no browser opens), hidden secret entry, idempotent "
    "`.env` upserts, guided GitHub secret/variable steps, and a closing summary. **Your job is "
    "only to scope the procedure and author its stages.** The library above the `STAGES` "
    "marker is identical in every wizard; that consistency is the point: never hand-edit it.",
    "- For setup: the `.env` templates (`.env.example`, `.env.sample`, `.env.template`, "
    "`.env.dist`; never `.env` itself or any other `.env.*`, which hold live values) and "
    "`.github/workflows/*` (every `secrets.*` / `vars.*` reference is a value the wizard must "
    "produce).",
    "Copy `scripts/wizard_template.py` to the target path. Replace the example stage with one "
    "`stage` per step, in dependency order.",
    '- Check the syntax with `ast.parse`, which writes no `__pycache__/`: `python3 -c "import '
    "ast, pathlib, sys; ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))\" "
    "<script>`; run `ruff check` or `mypy` if available.",
    '- Make it executable with `os.chmod` (`python3 -c "import os, sys; os.chmod(sys.argv[1], '
    '0o755)" <script>`), or tell the user to run it as `python3 <script>`.',
)
_WIZARD_REPLACED = (
    "bash",
    "template.sh",
    "WSL",
    "`gh secret`",
    "shellcheck",
    "`chmod +x",
    "`.env.*`, `README`",
    "`docker-compose*`",
)


def test_wizard_frontmatter_adds_the_id_and_says_python() -> None:
    text = (_WIZARD / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith(
        f"---\nid: wizard\nname: wizard\ndescription: {_WIZARD_DESCRIPTION}\n---\n"
    )
    frontmatter, _ = split_skill("wizard")
    assert frontmatter == {"id": "wizard", "name": "wizard", "description": _WIZARD_DESCRIPTION}
    assert len(_WIZARD_DESCRIPTION) == 315


def test_wizard_skill_text() -> None:
    text = (_WIZARD / "SKILL.md").read_text(encoding="utf-8")
    frontmatter, body = split_skill("wizard")
    assert "interactive Python wizard" in str(frontmatter["description"])
    assert [t for t in _WIZARD_NEW_TEXTS if t not in text] == []
    assert [t for t in _WIZARD_REPLACED if t in text] == []
    for template in ("`.env.sample`", "`.env.template`", "`.env.dist`", "never `.env` itself"):
        assert template in body, template
    assert len(text.split("\n")) == 46, "45 lines plus the final newline (A.T07.2 Files)"


def test_wizard_skill_dir_holds_exactly_its_three_files() -> None:
    names = sorted(p.relative_to(_WIZARD).as_posix() for p in skill_files("wizard"))
    assert names == ["SKILL.md", "references/LICENSE", "scripts/wizard_template.py"]


# --- wizard: the template script (A.T07.2 changes 12-25) --------------------------

_STAGES_COMMENT = "# STAGES: author this section. One stage() per step the human takes."
_LIBRARY_ONLY = ("banner", "note", "warn", "finish", "run_wizard")
_PLACEHOLDER = "<Stripe dashboard, test mode: Developers → API keys>"
_EXAMPLE_STAGE = (
    f"    {_EXAMPLE_RULE}\n"
    '    stage("Stripe: API keys")\n'
    '    say("We\'ll grab your Stripe test keys and store them for local dev + CI.")\n'
    f'    open_url("{_PLACEHOLDER}")\n'
    '    step("On the API keys page, copy the Publishable key (starts pk_test_).")\n'
    '    stripe_publishable_key = ask("STRIPE_PUBLISHABLE_KEY", "Paste the publishable key:")\n'
    "    step(\"Click 'Reveal test key' on the Secret key row, then copy it.\")\n"
    '    stripe_secret_key = ask_secret("STRIPE_SECRET_KEY", "Paste the secret key:")\n'
    '    write_env("STRIPE_PUBLISHABLE_KEY", stripe_publishable_key)\n'
    '    write_env("STRIPE_SECRET_KEY", stripe_secret_key)\n'
    '    set_secret("STRIPE_SECRET_KEY", stripe_secret_key)  # CI needs this one\n'
    f"    {_RULE}\n"
)
_WIZARD_UPSTREAM_STRINGS = (
    "  You drive the browser; this wizard tells you exactly what to do and\\n",
    "  captures the values you copy back. Stop any time with Ctrl-C and re-run\\n",
    "  later, since it remembers values already saved.",
    " stages",
    "Ready to start?",
    "Press Enter to continue",
    "[Enter keeps current]",
    "✓ Setup complete",
    "still to do by hand:",
    "Generated by the `wizard` skill.",
    _PLACEHOLDER,
    f"# {'─' * 74}\n# Wizard library: delightful, consistent UX, identical across every wizard.\n",
    f"{_RULE}\n{_STAGES_COMMENT}\n"
    f"# Replace the example below. Set TOTAL_STAGES to match the stages you write.\n{_RULE}\n",
)
_SKILL_HELPERS_RE = re.compile(r"Use the library helpers:([^.]*)\.")


def _wizard(cwd: Path, **scenario: object) -> dict[str, Any]:
    return run_script_scenario(_WIZARD_SCRIPT, dict(scenario), cwd)


def _wizard_no_terminal_message(script: Path) -> str:
    return (
        "This wizard needs a human at an interactive terminal, and stdin here is not one.\n"
        "Ask the user to run it in their own terminal:\n"
        f"    python3 {shlex.quote(str(script.resolve()))}\n"
    )


def _skill_helper_names() -> set[str]:
    text = (_WIZARD / "SKILL.md").read_text(encoding="utf-8")
    match = _SKILL_HELPERS_RE.search(text)
    assert match is not None, "SKILL L35 lists the library helpers"
    spans = [s.strip() for s in match.group(1).split(",")]
    return {name.strip("`") for span in spans for name in span.split("/")}


def _total_stages_assignments(tree: ast.Module) -> list[tuple[int, object]]:
    return [
        (node.lineno, ast.literal_eval(node.value))
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "TOTAL_STAGES" for t in node.targets)
    ]


def test_wizard_library_defines_every_helper_the_skill_names() -> None:
    source = _WIZARD_SCRIPT.read_text(encoding="utf-8")
    tree = _module_tree(_WIZARD_SCRIPT)
    marker = source.split("\n").index(_STAGES_COMMENT) + 1
    defs = _top_level_defs(tree)
    above = {name for name, line in defs.items() if line < marker}
    helpers = _skill_helper_names()
    assert helpers == {
        "stage", "say", "step", "open_url", "ask", "ask_secret", "write_env",
        "set_secret", "set_var", "pause", "confirm",
    }  # fmt: skip
    assert helpers | set(_LIBRARY_ONLY) <= above
    assert defs["wizard_stages"] > marker
    assignments = _total_stages_assignments(tree)
    assert [(line < marker, value) for line, value in assignments] == [(True, 0), (False, 1)]
    assert _is_main_block(tree.body[-1])
    assert source.endswith(
        'if __name__ == "__main__":\n    raise SystemExit(run_wizard(wizard_stages))\n'
    )


def test_wizard_template_keeps_upstream_strings() -> None:
    source = _WIZARD_SCRIPT.read_text(encoding="utf-8")
    assert len(_RULE) == len(_EXAMPLE_RULE) == 76
    assert [s for s in _WIZARD_UPSTREAM_STRINGS if s not in source] == []
    assert _EXAMPLE_STAGE in source
    assert '    banner("Stripe setup")\n' in source
    assert source.count(f"    {_RULE}\n") == 1
    for upstream in ("/wizard", "incl. WSL", "gh missing", "gh not ready", "set -euo pipefail"):
        assert upstream not in source, upstream


_WIZARD_SCRIPT_NEW_TEXTS = (
    "WRITTEN_ENV: list[str] = []  # KEYs written to ENV_FILE this run\n"
    "WRITTEN_SECRET: list[str] = []  # secret NAMEs set this run\n"
    "SKIPPED: list[str] = []  # things left for the human to do by hand\n"
    "WRITTEN_VAR: list[str] = []  # variable NAMEs set this run\n",
)
_WIZARD_DOCSTRINGS = {
    "confirm": 'confirm("question") is a y/N gate; returns success on yes.',
    "open_url": (
        "open_url(url) opens it in the human's browser through Python's webbrowser module; "
        "an argument without a scheme and host is only printed."
    ),
    "set_secret": (
        "set_secret(name, value) walks the human through adding a GitHub Actions repository "
        "secret by hand: it shows the name, never the value, waits for their confirmation and "
        'records it for the summary; a "no" leaves it on the still-to-do list.'
    ),
    "set_var": (
        "set_var(name, value) walks the human through adding a GitHub Actions repository "
        "variable (not secret) by hand: it shows the name and the value, waits for their "
        "confirmation and records it for the summary."
    ),
    "wizard_stages": (
        "The stages, in dependency order: banner first, one stage() per step, finish() last."
    ),
}


def test_wizard_template_new_texts_and_state_order() -> None:
    source = _WIZARD_SCRIPT.read_text(encoding="utf-8")
    tree = _module_tree(_WIZARD_SCRIPT)
    assert [t for t in _WIZARD_SCRIPT_NEW_TEXTS if t not in source] == []
    docstrings = {name: _docstring(tree, name) for name in _WIZARD_DOCSTRINGS}
    assert docstrings == _WIZARD_DOCSTRINGS


def _wizard_attributions() -> str:
    text = (PLUGIN_ROOT / "ATTRIBUTIONS.md").read_text(encoding="utf-8")
    section = text.split("\n### wizard\n", 1)[1].split("\n### ", 1)[0]
    return " ".join(section.split())


def test_wizard_attributions_name_the_removed_tools() -> None:
    section = _wizard_attributions()
    for named in (
        "the `gh secret`/`gh variable` writes become",
        "the `tput` colours (`tput bold`, `dim`, `sgr0`, `setaf`) become ANSI SGR codes",
        "the four OS openers (`wslview`, `explorer.exe`, `xdg-open`, `open`)",
        "(upstream 'e.g. gh missing')",
        "without the `gh secret set` command (and without the `gh auth status` check)",
        'global L177 should say `tput` instead of "the terminal-colour utility"',
    ):
        assert named in section, named
    for vague in ("terminal-colour utility becomes", "the forge CLI's secret", "(D22, D28)"):
        assert vague not in section, vague
    assert "(D22; the lint exemption is prS D24)" in section


def test_wizard_without_a_terminal_exits_2_and_touches_nothing(tmp_path: Path) -> None:
    proc = _run_without_a_terminal(_WIZARD_SCRIPT, tmp_path)
    assert proc.returncode == 2
    assert proc.stdout == "", "no banner"
    assert proc.stderr == _wizard_no_terminal_message(_WIZARD_SCRIPT)
    assert "Traceback" not in proc.stderr
    assert not (tmp_path / ".env").exists()


def test_wizard_run_ends_cleanly_on_eof(tmp_path: Path) -> None:
    report = _wizard(tmp_path, stdin=[], getpass=[], calls=[["__run__"]])
    assert _value(report) == 0
    assert "Traceback" not in report["stderr"]
    assert (tmp_path / ".env").read_bytes() == b"STRIPE_PUBLISHABLE_KEY=\nSTRIPE_SECRET_KEY=\n"
    assert report["state"]["SKIPPED"] == [
        "GitHub secret STRIPE_SECRET_KEY (set it by hand in the repo's CI settings)"
    ]


def test_write_env_creates_an_owner_only_file(tmp_path: Path) -> None:
    report = _wizard(tmp_path, calls=[["write_env", "A", "1"]])
    assert _value(report) is None
    assert (tmp_path / ".env").read_bytes() == b"A=1\n"
    if os.name == "posix":
        assert stat.S_IMODE((tmp_path / ".env").stat().st_mode) == 0o600
    assert report["stdout"] == "  ✓ wrote A → .env\n"
    assert report["state"]["WRITTEN_ENV"] == ["A"]


def _temp_files(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.glob(".env.*.tmp"))


def test_write_env_upserts_and_keeps_other_lines_byte_for_byte(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_bytes(b"# c\nA=old\nAB=keep\nexport A=x\nC=3\r\nX=\xff\nA=older\nD=4")
    expected = b"# c\nAB=keep\nexport A=x\nC=3\r\nX=\xff\nD=4\nA=new\n"
    _value(_wizard(tmp_path, calls=[["write_env", "A", "new"]]))
    assert env.read_bytes() == expected
    _value(_wizard(tmp_path, calls=[["write_env", "A", "new"]]))
    assert env.read_bytes() == expected, "a second identical upsert changes nothing"
    assert _temp_files(tmp_path) == []


def test_write_env_keeps_the_old_file_when_the_replace_fails(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_bytes(b"A=1\nB=2\n")
    report = _wizard(tmp_path, fail_replace=True, calls=[["write_env", "A", "3"]])
    assert _error(report) == ["OSError", "replace failed"]
    assert env.read_bytes() == b"A=1\nB=2\n"
    assert _temp_files(tmp_path) == []


def test_env_keys_must_be_identifiers(tmp_path: Path) -> None:
    report = _wizard(
        tmp_path, stdin=["x"], calls=[["write_env", "BAD KEY", "x"], ["ask", "1A", "q"]]
    )
    for index, key in enumerate(("BAD KEY", "1A")):
        kind, message = _error(report, index)
        assert kind == "ValueError"
        assert repr(key) in message
    assert not (tmp_path / ".env").exists()


@pytest.mark.parametrize(
    ("env", "expected"),
    [({}, ".env"), ({"ENV_FILE": ""}, ".env"), ({"ENV_FILE": "custom.env"}, "custom.env")],
)
def test_env_file_honours_the_environment_like_bash(
    tmp_path: Path, env: dict[str, str], expected: str
) -> None:
    report = _wizard(tmp_path, env=env, calls=[["__get__", "ENV_FILE"], ["write_env", "K", "v"]])
    assert _value(report) == expected
    assert (tmp_path / expected).read_bytes() == b"K=v\n"


def test_existing_reads_the_last_matching_line(tmp_path: Path) -> None:
    calls = [["_existing", "A"], ["_existing", "Z"]]
    assert [_value(_wizard(tmp_path, calls=calls), i) for i in (0, 1)] == ["", ""]
    (tmp_path / ".env").write_bytes(b"A=x=y\nAB=no\nA=last=one\n")
    report = _wizard(tmp_path, calls=calls)
    assert [_value(report, i) for i in (0, 1)] == ["last=one", ""]


def test_ask_offers_and_keeps_the_current_value(tmp_path: Path) -> None:
    ask = [["ask", "A", "Paste:"]]
    fresh = _wizard(tmp_path, stdin=["  typed \t"], calls=ask)
    assert (_value(fresh), fresh["stdout"]) == ("typed", "  Paste: ")
    (tmp_path / ".env").write_bytes(b"A=cur\n")
    kept = _wizard(tmp_path, stdin=[""], calls=ask)
    assert (_value(kept), kept["stdout"]) == ("cur", "  Paste: [Enter keeps current] ")
    # A.T07.2 says '"cur" is not in stdout', but "[Enter keeps current]" holds "cur":
    # the only "cur" is the one inside that hint, so the value itself is never printed.
    assert kept["stdout"].count("cur") == kept["stdout"].count("current") == 1
    assert _value(_wizard(tmp_path, stdin=["new"], calls=ask)) == "new"
    assert _value(_wizard(tmp_path, stdin=[], calls=ask)) == "cur", "end of file keeps it"


def test_ask_secret_reads_through_getpass_and_never_prints_the_value(tmp_path: Path) -> None:
    report = _wizard(tmp_path, getpass=["sk_test_9"], calls=[["ask_secret", "A", "Paste:"]])
    assert _value(report) == "sk_test_9"
    assert report["getpass_prompts"] == [""]
    assert "sk_test_9" not in report["stdout"] + report["stderr"]
    (tmp_path / ".env").write_bytes(b"A=cur\n")
    assert _value(_wizard(tmp_path, getpass=[], calls=[["ask_secret", "A", "Paste:"]])) == "cur"


def test_confirm_accepts_only_answers_starting_with_y(tmp_path: Path) -> None:
    answers = ["y", "Y", "yes", " y", "", "n", "no"]
    calls = [["confirm", "Go?"]] * (len(answers) + 1)  # the last one reads end of file
    report = _wizard(tmp_path, stdin=answers, calls=calls)
    assert [r["value"] for r in report["results"]] == [True] * 4 + [False] * 4
    one = _wizard(tmp_path, stdin=["n"], calls=[["confirm", "Go?"]])
    assert one["stdout"] == "  ? Go? [y/N] "


def test_pause_continues_on_end_of_file(tmp_path: Path) -> None:
    report = _wizard(tmp_path, stdin=[], calls=[["pause"]])
    assert _value(report) is None
    assert report["stdout"] == "  Press Enter to continue "


def _https(host: str, path: str) -> str:
    """A web address built from parts, so no URL is written in this file."""
    return "https" + "://" + host + path


def test_open_url_launches_only_a_url_with_scheme_and_host(tmp_path: Path) -> None:
    address = _https("example.test", "/keys")
    report = _wizard(tmp_path, browser="opens", calls=[["open_url", address]])
    assert report["browser_calls"] == [[address, 2]]
    assert report["stdout"] == f"  ↗ opening {address}\n"
    for argument in (_PLACEHOLDER, "localhost:3000", "Stripe: API keys"):
        printed = _wizard(tmp_path, browser="opens", calls=[["open_url", argument]])
        assert printed["browser_calls"] == []
        assert printed["stdout"] == f"  ↗ go to {argument}\n"


@pytest.mark.parametrize(
    ("browser", "warning"),
    [
        ("fails", "couldn't open a browser; visit it manually: "),
        ("raises", "couldn't open a browser, so visit it manually: "),
    ],
)
def test_open_url_warns_when_no_browser_opens(tmp_path: Path, browser: str, warning: str) -> None:
    address = _https("example.test", "/keys")
    report = _wizard(tmp_path, browser=browser, calls=[["open_url", address]])
    assert _value(report) is None
    assert report["stdout"] == f"  ↗ opening {address}\n  ⚠ {warning}{address}\n"


def test_set_secret_is_a_guided_step_that_never_shows_the_value(tmp_path: Path) -> None:
    done = _wizard(tmp_path, stdin=["y"], calls=[["set_secret", "S", "v4lue"]])
    assert done["state"]["WRITTEN_SECRET"] == ["S"]
    assert done["stdout"].endswith("  ✓ set GitHub secret S\n")
    assert "Settings → Secrets and variables → Actions → New repository secret." in done["stdout"]
    assert "v4lue" not in done["stdout"]
    for stdin in (["n"], []):
        skipped = _wizard(tmp_path, stdin=stdin, calls=[["set_secret", "S", "v4lue"]])
        assert skipped["state"]["SKIPPED"] == [
            "GitHub secret S (set it by hand in the repo's CI settings)"
        ]
        assert skipped["state"]["WRITTEN_SECRET"] == []
        assert "skipped GitHub secret S; set it later" in skipped["stdout"]
        assert "v4lue" not in skipped["stdout"]


def test_set_var_shows_the_value_and_records_it(tmp_path: Path) -> None:
    done = _wizard(tmp_path, stdin=["y"], calls=[["set_var", "V", "42"]])
    assert done["state"]["WRITTEN_VAR"] == ["V"]
    assert "give it this value: 42" in done["stdout"]
    assert (
        "In the GitHub repo: Settings → Secrets and variables → Actions → Variables → "
        "New repository variable." in done["stdout"]
    )
    assert done["stdout"].endswith("  ✓ set GitHub variable V\n")
    skipped = _wizard(tmp_path, stdin=["n"], calls=[["set_var", "V", "42"]])
    assert skipped["state"]["SKIPPED"] == ["GitHub variable V"]
    assert "skipped GitHub variable V; set it later" in skipped["stdout"]


def test_stage_counts_against_total_stages(tmp_path: Path) -> None:
    calls = [["stage", "First"], ["stage", "Second"]]
    report = _wizard(tmp_path, set={"TOTAL_STAGES": 3}, calls=calls)
    assert report["stdout"] == "\n▸ Stage 1/3 · First\n\n▸ Stage 2/3 · Second\n"
    assert report["state"]["_STAGE_INDEX"] == 2
    banner = _wizard(tmp_path, stdin=[], set={"TOTAL_STAGES": 3}, calls=[["banner", "T"]])
    assert _value(banner) is None
    assert "  3 stages" in banner["stdout"]


def test_clear_and_colours_need_a_terminal(tmp_path: Path) -> None:
    calls = [["stage", "X"], ["step", "s"]]
    colour = _wizard(tmp_path, stdout_tty=True, env={"TERM": "xterm-256color"}, calls=calls)
    assert colour["stdout"].startswith(_SCREEN_CLEAR)
    assert "\033[34m" in colour["stdout"]
    for scenario in (
        {"stdout_tty": True, "env": {"TERM": "dumb"}},
        {"stdout_tty": False, "env": {"TERM": "xterm-256color"}},
    ):
        plain = _wizard(tmp_path, calls=calls, **scenario)
        assert "\033" not in plain["stdout"], scenario


def test_finish_summarises_everything(tmp_path: Path) -> None:
    state = {"WRITTEN_ENV": ["A", "B"], "WRITTEN_SECRET": ["S"], "WRITTEN_VAR": ["V"]}
    report = _wizard(tmp_path, set={**state, "SKIPPED": ["x"]}, calls=[["finish"]])
    assert report["stdout"] == (
        "\n  ✓ Setup complete\n  wrote 2 value(s) to .env: A B\n  set 1 GitHub secret(s): S\n"
        "  set 1 GitHub variable(s): V\n\n  ⚠ still to do by hand:\n    - x\n\n"
    )


def test_run_wizard_ctrl_c_exits_130_with_the_stop_note(tmp_path: Path) -> None:
    report = _wizard(tmp_path, stdin=["", "x"], interrupt_on_read=1, calls=[["__run__"]])
    assert _value(report) == 130
    assert report["stdout"].endswith(
        "  ⚠ stopped. Re-run it later; it remembers values already saved.\n"
    )
    assert "Traceback" not in report["stderr"]
    assert not (tmp_path / ".env").exists()


def test_template_example_runs_end_to_end_and_reruns_idempotently(tmp_path: Path) -> None:
    expected = b"STRIPE_PUBLISHABLE_KEY=pk_test_123\nSTRIPE_SECRET_KEY=sk_test_456\n"
    first = _wizard(
        tmp_path, stdin=["", "pk_test_123", "y"], getpass=["sk_test_456"], calls=[["__run__"]]
    )
    assert _value(first) == 0
    assert (tmp_path / ".env").read_bytes() == expected
    assert first["browser_calls"] == [], "the placeholder is printed, never launched"
    assert "sk_test_456" not in first["stdout"]
    assert "set 1 GitHub secret(s): STRIPE_SECRET_KEY" in first["stdout"]
    second = _wizard(tmp_path, stdin=["", "", "y"], getpass=[""], calls=[["__run__"]])
    assert _value(second) == 0
    assert (tmp_path / ".env").read_bytes() == expected
    assert second["stdout"].count("[Enter keeps current]") == 2
