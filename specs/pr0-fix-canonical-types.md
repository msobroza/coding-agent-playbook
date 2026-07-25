# PR 0-fix — canonical types round-trip bug fixes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three round-trip / invariant bugs in `src/coding_agent_playbook/types.py` surfaced by `/ultrareview` on PR 2 (canonical types), so PR A (detector + renderer + filesystem sources) can rely on the round-trip contract documented in SPEC §6.6.3.

**Architecture:** Three focused bug fixes inside the same file (`types.py`), each landing as its own commit with its own regression test. No new files, no new public API surface. All three fixes preserve the existing `from_markdown` / `to_markdown` / `to_dict` / `from_dict` signatures — pure semantics-correction in the function bodies.

**Tech Stack:** Python 3.12, dataclasses, PyYAML, pytest.

---

## Context for the fresh engineer

You are working in a git worktree off `main` of [coding-agent-playbook](https://github.com/msobroza/coding-agent-playbook). The repo is a Python-first engine described in `SPEC.md` (read §6.6 — that's the round-trip contract you're protecting).

PR 2 (already merged on `main`) introduced canonical dataclasses (`Rule`, `Prompt`, `Skill`) with markdown ↔ dataclass ↔ dict round-tripping. The `/ultrareview` multi-agent code review found three bugs in that PR. This plan fixes all three.

Repo conventions:
- Python 3.12, `uv` for env management.
- `ruff` for lint+format, `mypy` strict, `pytest` for tests.
- Run the suite with `uv run pytest` from repo root.
- **Commit authorship:** all commits authored solely by the user (`msobroza`). **Never add `Co-Authored-By:` trailers.** **Never pass `--author`.** This overrides any default tooling behavior.

## File structure

Only two files change in this PR. Both already exist.

| File | Responsibility | What changes |
| --- | --- | --- |
| `src/coding_agent_playbook/types.py` | Canonical types + markdown helpers | Tighten `split_frontmatter` closing-fence check; add `__post_init__` to `RuleFrontmatter`/`PromptFrontmatter` to coerce `None` → dataclass defaults; deep-copy `frontmatter` in `Skill.to_dict`/`from_dict` |
| `tests/unit/test_types.py` | Round-trip tests | Add three regression tests, one per bug |

No new modules, no new public functions. Field shapes in `RuleFrontmatter` / `PromptFrontmatter` / `Skill` do not change.

---

## Task 1: Fix bug_006 — `split_frontmatter` matches indented `---` as closing fence

**Bug summary.** `split_frontmatter` uses `lines[index].strip() == "---"` to find the closing fence. PyYAML serializes multi-line string scalars as quoted blocks whose continuation lines are indented by two spaces. If a frontmatter string value contains a line whose content is `---` (e.g. a description with an embedded markdown horizontal rule), PyYAML emits `  ---` and `.strip()` collapses that into a false fence match. Round-trip breaks; the failure surfaces as `yaml.scanner.ScannerError`, not the documented `ValueError`.

**Fix.** Match the fence without stripping leading whitespace. For symmetry, tighten the opening-fence check the same way.

**Files:**
- Modify: `src/coding_agent_playbook/types.py:25-36`
- Test: `tests/unit/test_types.py` (append)

- [ ] **Step 1: Write the failing regression test**

Append to `tests/unit/test_types.py`:

```python
def test_split_frontmatter_rejects_indented_closing_fence():
    """An indented '---' inside a YAML multi-line scalar must not be treated
    as the closing fence (bug_006 — round-trip regression)."""
    text = (
        "---\n"
        "id: x\n"
        "name: x\n"
        "description: 'line one\n"
        "\n"
        "  ---\n"
        "\n"
        "  line two'\n"
        "scope: scoped\n"
        "---\n"
        "body\n"
    )
    data, body = split_frontmatter(text)
    assert data["description"] == "line one\n---\nline two"
    assert body == "body\n"


def test_rule_markdown_roundtrip_with_horizontal_rule_in_description(tmp_path):
    """Rule with a '---' line inside its description round-trips through markdown
    (bug_006 — the round-trip contract from SPEC §6.6.3)."""
    rule = Rule(
        frontmatter=RuleFrontmatter(
            id="x",
            name="x",
            description="line one\n---\nline two",
            scope="scoped",
        ),
        body="body\n",
        template_body="body\n",
        is_templated=False,
        source_path=tmp_path / "rule.md",
        source_package="pkg",
    )
    path = tmp_path / "rule.md"
    path.write_text(rule.to_markdown(), encoding="utf-8")
    assert Rule.from_markdown(path, "pkg") == rule
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_types.py::test_split_frontmatter_rejects_indented_closing_fence tests/unit/test_types.py::test_rule_markdown_roundtrip_with_horizontal_rule_in_description -v`

Expected: both FAIL. The first fails because `split_frontmatter` truncates the YAML before the real closing fence, raising `yaml.scanner.ScannerError` (or a `ValueError` about a non-mapping, depending on what gets fed to `yaml.safe_load`). The second fails for the same reason on re-parse.

- [ ] **Step 3: Tighten the fence check in `split_frontmatter`**

Replace the body of `split_frontmatter` in `src/coding_agent_playbook/types.py:25-36`:

```python
def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split ``---\\n<yaml>\\n---\\n<body>`` into a (frontmatter mapping, body)."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != _FENCE:
        raise ValueError("artifact must start with a '---' frontmatter fence")
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r\n") == _FENCE:
            data = yaml.safe_load("".join(lines[1:index])) or {}
            if not isinstance(data, dict):
                raise ValueError("frontmatter must be a YAML mapping")
            return data, "".join(lines[index + 1 :])
    raise ValueError("unterminated frontmatter: missing closing '---'")
```

The change: `.strip()` → `.rstrip("\r\n")` on both fence checks. Now only column-0 fences match; indented `  ---` continuation lines are correctly treated as YAML content.

- [ ] **Step 4: Run the full test file to verify nothing else broke**

Run: `uv run pytest tests/unit/test_types.py -v`

Expected: all tests PASS, including the two new ones from Step 1 and the pre-existing `test_split_frontmatter_requires_opening_fence` (which uses `"no frontmatter here"` — that line still doesn't equal `"---"` after `rstrip`, so the ValueError still fires).

- [ ] **Step 5: Commit**

```bash
git add src/coding_agent_playbook/types.py tests/unit/test_types.py
git commit -m "fix(types): treat only column-0 '---' as frontmatter fence

split_frontmatter previously used .strip() to match the closing fence,
which matched indented '---' continuation lines that PyYAML emits inside
quoted multi-line scalars. A description containing a markdown horizontal
rule silently broke round-trip with an opaque ScannerError.

Now both opening and closing fence checks use rstrip(newline only).
Regression tests cover an indented fence inside a quoted scalar and a
full Rule.to_markdown/from_markdown round-trip with '---' in description.

Refs: SPEC §6.6.3 round-trip contract; /ultrareview bug_006."
```

---

## Task 2: Fix bug_001 — null-valued frontmatter fields violate types and break round-trip

**Bug summary.** When a YAML key is written with no value (e.g. `globs:` on its own line), PyYAML parses it as `None`. Dataclasses do **not** coerce an explicit `None` to the field's `default_factory` or `default` — `None` overrides the default. So `RuleFrontmatter(globs=None)` has `globs is None`, violating the declared `list[str]` type. Then `_without_empty` drops `None` on serialize; re-parse applies the default `[]`; original `!=` re-parsed.

Same pattern hits every defaulted field on `RuleFrontmatter` (`version`, `globs`, `applies_if`, `priority`, `tags`) and `PromptFrontmatter` (`version`, `applies_if`, `input_variables`, `includes_rules`, `eval_tasks`).

**Fix.** Add `__post_init__` to each frontmatter dataclass that coerces `None` → the appropriate default for every Optional-with-default field. This enforces the invariant at the dataclass boundary, so direct construction, `from_markdown`, and `from_dict` all get it right.

**Files:**
- Modify: `src/coding_agent_playbook/types.py:55-65` (RuleFrontmatter)
- Modify: `src/coding_agent_playbook/types.py:110-120` (PromptFrontmatter)
- Test: `tests/unit/test_types.py` (append)

- [ ] **Step 1: Write the failing regression tests**

Append to `tests/unit/test_types.py`:

```python
def test_rule_frontmatter_coerces_none_to_defaults():
    """YAML 'globs:' (blank) parses as None; the dataclass must coerce that
    back to the declared default so the field type holds (bug_001)."""
    fm = RuleFrontmatter(
        id="x",
        name="x",
        description="x",
        scope="scoped",
        version=None,  # type: ignore[arg-type]
        globs=None,  # type: ignore[arg-type]
        applies_if=None,  # type: ignore[arg-type]
        priority=None,  # type: ignore[arg-type]
        tags=None,  # type: ignore[arg-type]
    )
    assert fm.version == 1
    assert fm.globs == []
    assert fm.applies_if == {}
    assert fm.priority == 50
    assert fm.tags == []


def test_prompt_frontmatter_coerces_none_to_defaults():
    """Same coercion contract for PromptFrontmatter (bug_001)."""
    fm = PromptFrontmatter(
        id="x",
        name="x",
        description="x",
        slash="x",
        version=None,  # type: ignore[arg-type]
        applies_if=None,  # type: ignore[arg-type]
        input_variables=None,  # type: ignore[arg-type]
        includes_rules=None,  # type: ignore[arg-type]
        eval_tasks=None,  # type: ignore[arg-type]
    )
    assert fm.version == 1
    assert fm.applies_if == {}
    assert fm.input_variables == []
    assert fm.includes_rules == []
    assert fm.eval_tasks == []


def test_rule_markdown_roundtrip_with_blank_optional_fields(tmp_path):
    """A rule authored with blank 'globs:' / 'priority:' lines round-trips
    through markdown (bug_001 — SPEC §6.6.3 contract)."""
    text = (
        "---\nid: x\nname: x\ndescription: x\nscope: scoped\nglobs:\npriority:\ntags:\n---\nbody\n"
    )
    path = tmp_path / "rule.md"
    path.write_text(text, encoding="utf-8")
    rule = Rule.from_markdown(path, "pkg")
    assert rule.frontmatter.globs == []
    assert rule.frontmatter.priority == 50
    assert rule.frontmatter.tags == []
    path.write_text(rule.to_markdown(), encoding="utf-8")
    assert Rule.from_markdown(path, "pkg") == rule
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_types.py::test_rule_frontmatter_coerces_none_to_defaults tests/unit/test_types.py::test_prompt_frontmatter_coerces_none_to_defaults tests/unit/test_types.py::test_rule_markdown_roundtrip_with_blank_optional_fields -v`

Expected: all three FAIL.
- Coercion tests fail with `AssertionError: assert None == 1` (or similar) — the dataclass kept `None`.
- Round-trip test fails because the first parsed rule has `globs=None`, `_without_empty` strips the key, re-parse applies default `[]`, so the two Rule objects compare unequal.

- [ ] **Step 3: Add `__post_init__` to `RuleFrontmatter`**

Replace `src/coding_agent_playbook/types.py:55-65`:

```python
@dataclass
class RuleFrontmatter:
    id: str
    name: str
    description: str
    scope: Literal["always", "scoped"]
    version: int = 1
    globs: list[str] = field(default_factory=list)
    applies_if: dict[str, Any] = field(default_factory=dict)
    priority: int = 50
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.version is None:
            self.version = 1
        if self.globs is None:
            self.globs = []
        if self.applies_if is None:
            self.applies_if = {}
        if self.priority is None:
            self.priority = 50
        if self.tags is None:
            self.tags = []
```

- [ ] **Step 4: Add `__post_init__` to `PromptFrontmatter`**

Replace `src/coding_agent_playbook/types.py:110-120`:

```python
@dataclass
class PromptFrontmatter:
    id: str
    name: str
    description: str
    slash: str
    version: int = 1
    applies_if: dict[str, Any] = field(default_factory=dict)
    input_variables: list[dict[str, Any]] = field(default_factory=list)
    includes_rules: list[str] = field(default_factory=list)
    eval_tasks: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.version is None:
            self.version = 1
        if self.applies_if is None:
            self.applies_if = {}
        if self.input_variables is None:
            self.input_variables = []
        if self.includes_rules is None:
            self.includes_rules = []
        if self.eval_tasks is None:
            self.eval_tasks = []
```

- [ ] **Step 5: Run the three new tests to verify they pass**

Run: `uv run pytest tests/unit/test_types.py::test_rule_frontmatter_coerces_none_to_defaults tests/unit/test_types.py::test_prompt_frontmatter_coerces_none_to_defaults tests/unit/test_types.py::test_rule_markdown_roundtrip_with_blank_optional_fields -v`

Expected: all three PASS.

- [ ] **Step 6: Run the whole test file to verify nothing regressed**

Run: `uv run pytest tests/unit/test_types.py -v`

Expected: all tests PASS (the new ones plus all pre-existing ones).

- [ ] **Step 7: Commit**

```bash
git add src/coding_agent_playbook/types.py tests/unit/test_types.py
git commit -m "fix(types): coerce None to defaults in frontmatter dataclasses

YAML parses 'globs:' (blank value) as None. Dataclass keyword defaults
do not fire when None is explicitly passed, so RuleFrontmatter(globs=None)
held None, violating its declared list[str] type. _without_empty stripped
the key on serialize, and re-parse applied the default, breaking the
markdown round-trip contract documented in SPEC §6.6.3.

Add __post_init__ to RuleFrontmatter and PromptFrontmatter that coerces
None to the appropriate default for every Optional-with-default field.

Regression tests cover direct construction (None override) and a full
markdown round-trip with blank optional YAML fields.

Refs: SPEC §6.6.3; /ultrareview bug_001."
```

---

## Task 3: Fix bug_002 — `Skill.to_dict` / `from_dict` leak the frontmatter dict by reference

**Bug summary.** `Skill.to_dict` returns `self.frontmatter` directly (live reference, not a copy). Symmetrically `Skill.from_dict` stores `data["frontmatter"]` by reference. `Rule` and `Prompt` go through `dataclasses.asdict`, which deep-copies — so `Skill` is the asymmetric outlier. Latent today, but the moment a downstream PR does serialize → augment → write with a Skill, mutations leak.

**Fix.** Copy the frontmatter dict at both serialization boundaries. Same one-line change on each side.

**Files:**
- Modify: `src/coding_agent_playbook/types.py:181-200`
- Test: `tests/unit/test_types.py` (append)

- [ ] **Step 1: Write the failing regression tests**

Append to `tests/unit/test_types.py`:

```python
def test_skill_to_dict_does_not_alias_frontmatter():
    """to_dict must return a snapshot; mutating it must not mutate the Skill
    (bug_002 — matches the Rule/Prompt detached-snapshot contract)."""
    skill = Skill(
        frontmatter={"name": "demo"},
        body="b",
        scripts_dir=None,
        references_dir=None,
        source_package="pkg",
    )
    data = skill.to_dict()
    assert data["frontmatter"] is not skill.frontmatter
    data["frontmatter"]["injected"] = True
    assert "injected" not in skill.frontmatter


def test_skill_from_dict_does_not_alias_frontmatter():
    """from_dict must detach from its input; mutating the dict must not
    mutate the resulting Skill (bug_002)."""
    payload = {
        "frontmatter": {"name": "demo"},
        "body": "b",
        "scripts_dir": None,
        "references_dir": None,
        "source_package": "pkg",
    }
    skill = Skill.from_dict(payload)
    payload["frontmatter"]["injected"] = True
    assert "injected" not in skill.frontmatter
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_types.py::test_skill_to_dict_does_not_alias_frontmatter tests/unit/test_types.py::test_skill_from_dict_does_not_alias_frontmatter -v`

Expected: both FAIL. The first fails on the `is not` assertion (the dict IS aliased). The second fails on `assert "injected" not in skill.frontmatter` (the mutation leaked through).

- [ ] **Step 3: Copy the frontmatter dict in `Skill.to_dict`**

In `src/coding_agent_playbook/types.py:181-188`, change:

```python
    def to_dict(self) -> dict[str, Any]:
        return {
            "frontmatter": self.frontmatter,
            "body": self.body,
            "scripts_dir": None if self.scripts_dir is None else str(self.scripts_dir),
            "references_dir": None if self.references_dir is None else str(self.references_dir),
            "source_package": self.source_package,
        }
```

to:

```python
    def to_dict(self) -> dict[str, Any]:
        return {
            "frontmatter": dict(self.frontmatter),
            "body": self.body,
            "scripts_dir": None if self.scripts_dir is None else str(self.scripts_dir),
            "references_dir": None if self.references_dir is None else str(self.references_dir),
            "source_package": self.source_package,
        }
```

- [ ] **Step 4: Copy the frontmatter dict in `Skill.from_dict`**

In `src/coding_agent_playbook/types.py:190-200`, change:

```python
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Skill:
        scripts_dir = data["scripts_dir"]
        references_dir = data["references_dir"]
        return cls(
            data["frontmatter"],
            data["body"],
            None if scripts_dir is None else Path(scripts_dir),
            None if references_dir is None else Path(references_dir),
            data["source_package"],
        )
```

to:

```python
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Skill:
        scripts_dir = data["scripts_dir"]
        references_dir = data["references_dir"]
        return cls(
            dict(data["frontmatter"]),
            data["body"],
            None if scripts_dir is None else Path(scripts_dir),
            None if references_dir is None else Path(references_dir),
            data["source_package"],
        )
```

- [ ] **Step 5: Run the two new tests to verify they pass**

Run: `uv run pytest tests/unit/test_types.py::test_skill_to_dict_does_not_alias_frontmatter tests/unit/test_types.py::test_skill_from_dict_does_not_alias_frontmatter -v`

Expected: both PASS.

- [ ] **Step 6: Run the whole test file to verify nothing regressed**

Run: `uv run pytest tests/unit/test_types.py -v`

Expected: all tests PASS, including the pre-existing `test_skill_dict_roundtrip` (which exercises `Skill.from_dict(skill.to_dict())` — that path still works, it just no longer aliases).

- [ ] **Step 7: Commit**

```bash
git add src/coding_agent_playbook/types.py tests/unit/test_types.py
git commit -m "fix(types): copy frontmatter dict in Skill.to_dict and from_dict

Skill.to_dict returned self.frontmatter by reference (and from_dict
stored data['frontmatter'] by reference), so mutating either side
leaked into the other. Rule and Prompt go through dataclasses.asdict
which deep-copies — Skill was the asymmetric outlier.

Both sides now wrap with dict(...). Regression tests verify mutation
isolation in both directions.

Refs: /ultrareview bug_002."
```

---

## Task 4: Final verification + PR

- [ ] **Step 1: Run the full test suite**

Run from repo root: `uv run pytest -v`

Expected: all tests PASS across `tests/unit/` (types, adapter base, sources base, CLI, entry points). No new test files were added — only `tests/unit/test_types.py` grew.

- [ ] **Step 2: Run ruff format + lint**

Run from repo root:

```bash
uv run ruff format src tests
uv run ruff check src tests
```

Expected: format makes no changes (or whatever changes are made are committed in Step 5). Lint reports zero issues.

- [ ] **Step 3: Run mypy in strict mode**

Run from repo root: `uv run mypy src`

Expected: zero errors. Note: the regression tests use `# type: ignore[arg-type]` on the intentional `None` arguments — those suppress the expected mypy complaints about passing `None` where `int` / `list[str]` / `dict[...]` is declared.

- [ ] **Step 4: If ruff format made any changes, commit them**

```bash
git status
# if there are unstaged changes:
git add -u
git commit -m "style: apply ruff format"
```

If `git status` shows a clean tree, skip the commit.

- [ ] **Step 5: Push the branch and open the PR**

```bash
git push -u origin HEAD
gh pr create \
  --title "PR 0-fix — canonical types round-trip bug fixes" \
  --body "$(cat <<'EOF'
Fixes three bugs surfaced by `/ultrareview` on PR 2 (canonical types). All in `src/coding_agent_playbook/types.py`; PR A (detector + renderer + filesystem sources) is unblocked once this lands.

## Bugs fixed

| # | Severity | What | Commit |
| --- | --- | --- | --- |
| bug_006 | normal | \`split_frontmatter\` treated indented \`---\` continuation lines as the closing fence, breaking round-trip for any description containing a markdown horizontal rule | fix(types): treat only column-0 '---' as frontmatter fence |
| bug_001 | normal | Null-valued YAML fields (\`globs:\` blank) bypassed dataclass defaults, violated declared types, and broke markdown round-trip | fix(types): coerce None to defaults in frontmatter dataclasses |
| bug_002 | nit | \`Skill.to_dict\` / \`from_dict\` leaked the frontmatter dict by reference (asymmetric vs Rule/Prompt's \`dataclasses.asdict\` deep-copy) | fix(types): copy frontmatter dict in Skill.to_dict and from_dict |

## Round-trip contract restored

After this PR, the SPEC §6.6.3 contract holds for:
- Multi-line string scalars containing \`---\` (markdown horizontal rules in descriptions).
- Blank optional YAML fields (\`globs:\`, \`priority:\`, \`tags:\`, etc.).
- \`Skill.from_dict(skill.to_dict())\` produces a fully-detached \`Skill\`.

## Test coverage

7 new regression tests in \`tests/unit/test_types.py\`, one or two per bug. Full suite green (\`uv run pytest\` + \`ruff check\` + \`mypy\`).
EOF
)"
```

The PR title and body deliberately avoid mentioning the AI reviewer's report ID format — the commit messages already cite \`/ultrareview\` for traceability. **Do not add a \`Co-Authored-By:\` trailer** (repo policy: all commits authored solely by `msobroza`).

- [ ] **Step 6: Report back to the dispatcher**

Print a final summary to stdout:

```
PR 0-fix complete.
- Commits: 3 (one per bug) + 0-1 style (only if ruff format changed anything)
- Tests added: 7 regression tests in tests/unit/test_types.py
- Tests passing: <N>/<N>  (where N is the new total)
- ruff: clean
- mypy: clean
- PR URL: <gh-pr-create output URL>
```

The dispatcher (the human-facing session) takes over from here for the user-gate review.

---

## Self-review (filled in by the plan author)

**1. Spec coverage.**
- bug_006: Task 1 ✓
- bug_001: Task 2 ✓
- bug_002: Task 3 ✓
- Integration + PR: Task 4 ✓
- No spec gaps.

**2. Placeholder scan.** No TBD/TODO/"implement later"; every step has the actual code or actual command.

**3. Type consistency.**
- `RuleFrontmatter` fields after Task 2: `id, name, description, scope, version, globs, applies_if, priority, tags` — unchanged.
- `PromptFrontmatter` fields after Task 2: `id, name, description, slash, version, applies_if, input_variables, includes_rules, eval_tasks` — unchanged.
- `Skill.to_dict` / `from_dict` signatures after Task 3: unchanged (`dict[str, Any]` ↔ `Skill`).
- `split_frontmatter` signature after Task 1: unchanged.
- No new public methods, no new fields. No type drift across tasks.
