# PR C — Content extraction Implementation Plan

> **Rename note (v0.20).** This design shipped the tree as `content/`; v0.20 renamed it
> `catalog/`: the wheel's `_content/` is `_catalog/`, `bundled_content.py` is `catalog.py`
> (`catalog_root`, `catalog_layer_root`, `CatalogMissingError`, `catalog_dir=`),
> `tests/_content.py` is `tests/_catalog.py`, and the `content` pytest marker is
> `catalog`. The text below uses the current names; test-file names it cites may predate the rename.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move every rule, prompt, eval task and bundled skill out of
`src/coding_agent_playbook/` into a top-level `catalog/` tree, and rename
packs to bundled plugins (old names keep working as a deprecated alias).
Installed-wheel behaviour must not change.

**Architecture:**
- A new leaf module, `catalog.py`, is the only code that knows where
  `catalog/` lives: in the installed wheel it is `<pkg>/_catalog`, and in a
  source checkout it is `<repo>/catalog`.
- `_resource_subdir` routes the engine and plugin names to it. Third-party
  overlays keep today's `importlib.resources` path untouched.
- Hatch force-includes `catalog/` into the wheel as `coding_agent_playbook/_catalog`.
- Bundled plugins are directories, not Python modules.

**Tech Stack:** Python 3.12+, hatchling, pytest, ruff, mypy (strict), pip-only CI.

**Spec:** `specs/prC-content-extraction.md`. Read it before any task. It is
the authority for every string, rule and acceptance criterion this plan cites.

## Global Constraints

**Tooling**
- All commands run from the worktree root with its venv: `.venv/bin/python`,
  `.venv/bin/pytest`, `.venv/bin/ruff`, `.venv/bin/mypy`.
- The task gate is the CI gate:
  ```bash
  .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy && .venv/bin/pytest -q -p no:cacheprovider
  ```
  Coverage must stay at or above 80%. `filterwarnings = error` and
  `--strict-config` stay on.
- Every task ends green on the full gate. Never commit red.

**Git**
- Use `git mv` for every move: history must follow, and the 10 executable
  scripts must stay `100755`. Never copy and delete.
- Commits are authored by the configured user only (`msobroza`). Add no
  `Co-Authored-By` trailer, and never use `--author` or `-S`.
- Never commit `CLAUDE.md`, `.claude/`, `AGENTS.md`, `.opencode/`, `.agents/`
  or `shared_skills/`.

**Content**
- Vendored superpowers files stay byte-identical. That includes all 15
  `references/LICENSE` copies, which must equal the plugin `LICENSE`.
- Plugin skill scripts must stay valid on Python 3.10.

**Code style**
- Every new public function has full type hints and a docstring with an
  `Example::`.
- Functions are about 4–20 lines with nesting at most 2 deep. Errors carry the
  offending value.

**Exact strings (copied from the spec):**

| Item | Value |
| --- | --- |
| `ENGINE_PACKAGE` | `"coding_agent_playbook"` |
| `PLUGIN_NAMESPACE` | `"coding_agent_playbook.plugins"` |
| `DEPRECATED_PACK_NAMESPACE` | `"coding_agent_playbook.packs"` |
| `PACKAGED_CATALOG_DIRNAME` | `"_catalog"` |
| `CHECKOUT_CATALOG_DIRNAME` | `"catalog"` |
| Namespace reason | `the bundled plugin namespace, not a plugin` |
| Unknown plugin reason | `no such bundled plugin` |
| Hint | `" (bundled plugins: <comma-separated sorted dotted names>)"` |
| Config warning | `warning: <file>: overlays_enabled: '<old>' is deprecated; use '<new>'` |
| Flag warning | `warning: --overlays: '<old>' is deprecated; use '<new>'` |
| Missing-content error | `error: the engine's catalog was not found (looked in <a>, <b>); reinstall coding-agent-playbook` |
| Wheel force-include | `"catalog" = "coding_agent_playbook/_catalog"` |

**Baselines (session scratchpad, outside the repo):**
- Output-parity baseline: `parity-baseline/manifest.txt` (476 lines, 40 at
  `0o755`), generated from `parity-baseline/repo` by `manifest.py`.
- Baseline wheel: `parity-baseline/baseline.whl` (348 entries; 239 content
  files plus the engine LICENSE; 10 executable).

## Review Focus

1. **Both spellings listed together** (`packs.superpowers` and
   `plugins.superpowers`). Expected: sync succeeds, prints one warning line,
   and the plugin's skills are written. Pinned in Task 8.
2. **A bundled plugin that ships eval tasks and prompts, not only skills.**
   Expected: its tasks list with the plugin's `source_package`, and the prompt
   resolves next to them. Pinned in Task 6.
3. **A plugin directory added after a `git pull` in an editable install.**
   Expected: it is visible on the next call, without reinstalling. No caching.
   Pinned in Task 3.
4. **A typo under the old namespace** (`packs.superpower`). Expected: the
   warning recommends `plugins.superpower`, then preflight refuses it with
   `no such bundled plugin` plus the hint listing the real plugins. Pinned in
   Task 8.
5. **`init` with an unknown bundled plugin in the local file.** Expected: exit 2,
   the local file named, nothing written. Pinned in Task 7.

---

### Task 1: Non-vacuity safety net

Tests that pass silently when content is missing must fail loudly *before*
anything moves.

**Files:**
- Modify: `tests/integration/test_shipped_task_gates.py` (task parametrization, ~:62)
- Modify: `tests/integration/test_resources_self_contained.py` (rglob targets)
- Modify: `tests/packs/python_design/test_pack.py:89`
- Modify: `tests/cli/test_validate_links.py` (engine link gate, ~:186)

**Interfaces:** none; tests only.

- [ ] **Step 1:** In each file, assert that the collected set is non-empty
  before it is used. Examples: `assert _SHIPPED_TASKS, "no shipped eval tasks found"`
  at module level next to the parametrization source;
  `assert scanned, f"nothing scanned under {root}"` for the rglob;
  `assert skill_dirs, f"no skills under {SKILLS_ROOT}"`. For the link gate,
  assert that the walk visited at least one engine rule and one pack skill.
- [ ] **Step 2:** Prove that each assertion fires. Temporarily point each root at
  `tmp_path / "missing"`, or rename the dir locally. Run the module and see it
  fail with the new message. Revert.
- [ ] **Step 3:** Run the full gate. Expected: green, same counts as the
  baseline (2897 passed, 10 skipped).
- [ ] **Step 4:** Commit: `tests: fail loudly when shipped content is missing`.

---

### Task 2: One helper for content paths in tests (current locations)

**Files:**
- Create: `tests/_catalog.py`
- Modify (replace their own `parents[N] / "src" / "coding_agent_playbook" …` roots):
  - `tests/evals/test_prompting.py:28-29`
  - `tests/integration/test_find_injected_vuln_prompt.py:14`
  - `tests/integration/test_resources_self_contained.py:44-48`
  - `tests/integration/test_shipped_eval_tasks_c7.py:77`
  - `tests/integration/test_shipped_task_gates.py:63`
  - `tests/integration/test_crosscommitvuln_fixtures.py:31-32`
  - `tests/integration/test_modoboa_cmdi_fixture.py:18-19`
  - `tests/evaluators/test_eval_runner.py:322-324, 837-839`
  - `tests/packs/python_design/test_detect_smells.py:30`
  - `tests/packs/python_design/test_layer_map.py:27`
  - `tests/packs/python_design/test_lcom4_clusters.py:26`
  - `tests/packs/python_design/test_worked_example.py:19`

**Interfaces:**
- Produces, in `tests/_catalog.py`, all of type `Path`, anchored on
  `REPO_ROOT = Path(__file__).resolve().parents[1]`:
  - `CORE_ROOT`: today `REPO_ROOT / "src/coding_agent_playbook/resources"`.
  - `PLUGINS_ROOT`: today `REPO_ROOT / "src/coding_agent_playbook/packs"`.
  - `plugin_root(name: str) -> Path`: today `PLUGINS_ROOT / name / "resources"`.
    This is the directory holding `skills/`.
  - `plugin_files_root(name: str) -> Path`: today `PLUGINS_ROOT / name`. This
    is the directory holding `LICENSE` and `ATTRIBUTIONS.md`.

  Task 6 repoints these to `catalog/` without changing any caller.

- [ ] **Step 1:** Create `tests/_catalog.py` with the names above and a module
  docstring. Its rationale: anchored on the checkout, not on the production
  resolver, so path pins stay independent of the code under test.
- [ ] **Step 2:** Switch each listed module to import from `tests._catalog`.
  Keep the local constant names (e.g. `_SHIPPED_TASKS = CORE_ROOT / "eval_tasks"`)
  so diffs stay small.
- [ ] **Step 3:** Run `grep -rn '"src" / "coding_agent_playbook"' tests`.
  Expected: no hits.
- [ ] **Step 4:** Run the full gate. Expected: green, same test count.
- [ ] **Step 5:** Commit: `tests: centralize shipped-content paths in tests/_catalog.py`.

---

### Task 3: `catalog.py` resolver (pure, not yet wired)

**Files:**
- Create: `src/coding_agent_playbook/catalog.py`
- Test: `tests/unit/test_catalog.py`

**Interfaces:**
- Produces the constants and functions listed below, exactly as the spec's
  "`catalog.py` (new)" section defines them.
  - `_PACKAGE_DIR: Path = Path(__file__).resolve().parent`.
  - `class CatalogMissingError(RuntimeError)`, with
    `tried: tuple[Path, ...]` and a `str()` that lists the paths.
  - `catalog_root(package_dir: Path | None = None) -> Path`
  - `bundled_plugins(catalog_dir: Path | None = None) -> list[str]`
  - `canonical_overlay_name(name: str) -> str`
  - `canonical_overlay_list(names: Iterable[str]) -> tuple[list[str], tuple[str, ...]]`
  - `is_plugin_namespace(name: str) -> bool`
  - `is_bundled_layer(name: str) -> bool`
  - `catalog_layer_root(name: str, *, catalog_dir: Path | None = None) -> Path | None`
- The module imports nothing from `coding_agent_playbook`, because
  `config.py` and `config_schema.py` will import it.

- [ ] **Step 1: Write the failing tests.** Build roots in `tmp_path` with a
  helper `_make_tree(root, plugins=("superpowers",))` that creates
  `core/rules/` and `plugins/<p>/skills/`. Tests:
  - `test_packaged_root_wins`: `pkg/_catalog/core` and `pkg/../../catalog/core`
    both exist, under `src/pkg`. Expect `catalog_root(pkg) == pkg / "_catalog"`.
  - `test_checkout_fallback`: only `<tmp>/catalog/core` exists, with
    `pkg = <tmp>/src/coding_agent_playbook`. Expect `<tmp>/content`.
  - `test_packaged_without_core_is_not_accepted`: `pkg/_catalog/plugins` exists
    but `core` does not, and there is no checkout. Expect
    `CatalogMissingError`, with both candidate paths in `.tried`.
  - `test_fallback_requires_src_parent`: `<tmp>/lib/pkg` with `<tmp>/catalog/core`
    raises.
  - `test_missing_root_message_names_both_paths`: `str(err)` contains both
    paths.
  - `test_bundled_plugins_lists_identifier_dirs_only`. Under `plugins/`, create
    `superpowers/`, `python_design/`, `.hidden/`, `_private/`, `__pycache__/`,
    `bad-name/` and a stray file `README.md`. Expect
    `["coding_agent_playbook.plugins.python_design", "coding_agent_playbook.plugins.superpowers"]`.
  - `test_bundled_plugins_sees_new_dir_without_caching` (Review Focus 3): call
    once, `mkdir plugins/new_one/skills`, call again, and expect the new name
    listed.
  - `test_canonical_overlay_name`, parametrized:
    - `packs.superpowers` → `plugins.superpowers`;
    - `coding_agent_playbook.packs` → unchanged;
    - `coding_agent_playbook.packsx.y` → unchanged;
    - `acme.rules` → unchanged;
    - `coding_agent_playbook.packs.` → unchanged (empty rest).
  - `test_canonical_overlay_list_keeps_order_and_duplicates`: input
    `["a", "coding_agent_playbook.packs.x", "coding_agent_playbook.plugins.x"]`
    gives `(["a", "…plugins.x", "…plugins.x"], ("coding_agent_playbook.packs.x",))`.
  - `test_is_plugin_namespace`: true only for the two bare names.
  - `test_is_bundled_layer`: true for the engine, `…plugins.x` and `…packs.x`.
    False for both bare namespaces, `acme`, and `coding_agent_playbook.pluginsx`.
  - `test_bundled_layer_root_engine_and_plugin`: the engine gives `<root>/core`.
    `…plugins.superpowers` and `…packs.superpowers` both give
    `<root>/plugins/superpowers`.
  - `test_bundled_layer_root_rejects_unsafe_leaves`, parametrized under both
    namespaces with leaves `""`, `".."`, `"../core"`, `"/tmp"`,
    `"superpowers.skills"`, `"superpowers/skills"`, `"Superpowers"`,
    `"__pycache__"`. Each gives `None`.
  - `test_bundled_layer_root_raises_when_root_missing`: called with no
    `catalog_dir` while `_PACKAGE_DIR` is monkeypatched to an empty tmp dir,
    it raises `CatalogMissingError`.
- [ ] **Step 2:** Run `.venv/bin/pytest tests/unit/test_catalog.py -q -p no:cacheprovider`.
  Expected: FAIL (module missing).
- [ ] **Step 3:** Implement the module.
  - `catalog_layer_root` compares the canonical name against the
    `bundled_plugins(...)` list. It never builds a path from unchecked text.
  - `_PACKAGE_DIR` is read at call time, as the default when `package_dir` is
    `None`, so tests can monkeypatch it.
  - The checkout root is `package_dir.parent.parent / "catalog"`.
- [ ] **Step 4:** Run the module tests, then the full gate. Expected: green.
- [ ] **Step 5:** Commit: `feat: catalog resolver for engine and plugin content`.

---

### Task 4: Eval path logic no longer searches for `resources`

This lands before the move because the move would otherwise break prompt
lookup for every engine task.

**Files:**
- Modify: `src/coding_agent_playbook/evals/prompting.py:243-280` (`_resolve_prompt` docstring, `_infer_prompts_dir`)
- Modify: `src/coding_agent_playbook/commands/eval.py:634-670` (`_display_source_path`)
- Test: `tests/evals/test_prompting.py`, `tests/cli/test_eval.py:330-410`

**Interfaces:**
- Consumes: `catalog.is_bundled_layer(name) -> bool`.
- Produces: `_infer_prompts_dir(task_toml: Path) -> Path | None` (same
  signature), and `_display_source_path(task: EvalTask) -> str` (same
  signature).

- [ ] **Step 1: Write the failing tests.**
  - `test_infer_prompts_dir_layers`, parametrized over
    `<x>/catalog/core/eval_tasks/t/task.toml`,
    `<x>/pkg/resources/eval_tasks/t/task.toml` and
    `<x>/playbook/eval_tasks/t/task.toml`. Each returns `<layer>/prompts`
    (`parents[2] / "prompts"`).
  - `test_infer_prompts_dir_non_task_path`: `<x>/t/task.toml` returns `None`.
  - `test_infer_prompts_dir_does_not_resolve_symlinks`: a symlinked task dir
    yields the unresolved layer's `prompts`.
  - In `test_eval.py`:
    - `:348` expects `"coding_agent_playbook/eval_tasks/task-a/"`.
    - `:366` stays `"playbook_rules_bnp/resources/eval_tasks/pii-scan/"`.
    - Replace the fallback test at `:369-401` with
      `test_display_source_path_depends_only_on_layer_and_dir`. It covers a
      bundled plugin task (`"coding_agent_playbook.plugins.x/eval_tasks/t/"`),
      an overlay with an odd parent layout (`"some_overlay/resources/eval_tasks/task-x/"`)
      and repo-local (`"playbook/eval_tasks/task-y/"`).
    - Add `test_display_source_path_uses_directory_not_task_id`, where
      `task.id != source_path.parent.name`.
- [ ] **Step 2:** Run both test modules. Expected: the new cases fail.
- [ ] **Step 3:** Implement both functions as the spec's "Eval path logic"
  section describes. The `<dir>` is `task.source_path.parent.name`. Update
  both docstrings. They no longer mention searching for a `resources` segment.
- [ ] **Step 4:** Run the full gate. Expected: green. Engine tasks still find
  their prompts because `resources/eval_tasks/<id>` gives `parents[2] == resources`.
- [ ] **Step 5:** Commit: `fix(eval): find prompts and label tasks by layer, not by a 'resources' path segment`.

---

### Task 5: Pre-commit template becomes engine-owned

**Files:**
- Move: `src/coding_agent_playbook/resources/precommit/config.yaml.j2` → `src/coding_agent_playbook/templates/precommit/config.yaml.j2` (`git mv`)
- Modify: `src/coding_agent_playbook/commands/init.py:281-301`
- Test: `tests/integration/test_precommit_template.py:3,18-24`; `tests/integration/test_resources_self_contained.py` (scan targets, `:211` prefixes)

**Interfaces:**
- Produces: `commands/init.py: precommit_template_dir(templates_root: Path | None = None) -> Path`, plus a
  `PrecommitTemplateMissingError(RuntimeError)` that carries the expected path.
  It is raised when the directory or `config.yaml.j2` is missing.
- Produces: `tests/_catalog.py: PRECOMMIT_TEMPLATE_DIR: Path`, computed as
  `Path(str(resources.files("coding_agent_playbook") / "templates" / "precommit"))`.

- [ ] **Step 1: Write the failing tests.**
  - `test_precommit_template_is_packaged`: `(precommit_template_dir() / "config.yaml.j2").is_file()`.
  - `test_precommit_template_dir_missing_raises`: call through an injectable
    parameter, `precommit_template_dir(templates_root=tmp_path)`. Expect
    `PrecommitTemplateMissingError` whose message contains
    `tmp_path / "precommit"`.
  - `test_resource_subdir_has_no_engine_precommit`:
    `_resource_subdir("coding_agent_playbook", "precommit") is None`.
  - In `test_resources_self_contained.py`, add an explicit target
    `scan_targets(PRECOMMIT_TEMPLATE_DIR, prefix="templates/precommit/", policy=lambda _: ScanPolicy(urls=True, markers=True))`
    and change the non-vacuity prefix `"precommit/"` to `"templates/precommit/"`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Do the `git mv`. Implement
  `precommit_template_dir(templates_root: Path | None = None) -> Path`, where
  the default root is the engine's `templates/` via `resources.files`. Use it
  in `_render_fresh_pre_commit`, replacing the `assert`.
- [ ] **Step 4:** Run the full gate. Expected: green (`init` tests render the
  same YAML).
- [ ] **Step 5:** Commit: `refactor(init): move the pre-commit template to templates/ and fail explicitly when missing`.

---

### Task 6: Move content to `catalog/` and route bundled lookups through the resolver

This is one atomic task. Content moving and lookups switching must land
together.

**Files:**
- Move (`git mv`, whole subtrees):
  - `src/coding_agent_playbook/resources/{ATTRIBUTIONS.md,rules,prompts,eval_tasks}` → `catalog/core/`
  - `src/coding_agent_playbook/packs/superpowers/resources/skills` → `catalog/plugins/superpowers/skills`
  - `src/coding_agent_playbook/packs/superpowers/{LICENSE,ATTRIBUTIONS.md}` → `catalog/plugins/superpowers/`
  - `src/coding_agent_playbook/packs/python_design/resources/skills` → `catalog/plugins/python_design/skills`
  - `src/coding_agent_playbook/packs/python_design/ATTRIBUTIONS.md` → `catalog/plugins/python_design/`
- Modify: `src/coding_agent_playbook/sources/filesystem.py:56-79` (`_resource_subdir`; fix the comment at :72-75)
- Modify: `src/coding_agent_playbook/commands/_sync_preflight.py:139-149` (`_unusable_reason`: bundled-layer branch)
- Modify: `pyproject.toml` (force-include; ruff `extend-exclude`, `per-file-target-version`; mypy `exclude`)
- Modify: `src/coding_agent_playbook/packs/{superpowers,python_design}/__init__.py` docstrings (point to `catalog/plugins/<n>/`). They are deleted in Task 7.
- Modify content path text:
  - the 10 `catalog/core/eval_tasks/find-injected-vuln-*/task.toml`;
  - `catalog/plugins/superpowers/ATTRIBUTIONS.md:3`.
- Modify tests:
  - `tests/_catalog.py`: repoint to `REPO_ROOT / "catalog" / ...`. `plugin_root`
    and `plugin_files_root` both become `PLUGINS_ROOT / name`.
  - `tests/packs/superpowers_expectations.py:139-141, 202-224`.
  - `tests/packs/python_design/test_pack.py:43-44, 112`.
  - `tests/integration/test_resources_self_contained.py:44-48, 211, 216-218`.
- Create tests: `tests/unit/test_sources_filesystem_bundled.py`

**Interfaces:**
- Consumes: `catalog.is_bundled_layer`, `catalog_layer_root`, and
  `CatalogMissingError` (Task 3).
- Produces:
  - `_resource_subdir(package: str, subdir: str) -> Path | None` (same
    signature). For bundled layers it may raise `CatalogMissingError`.
  - `superpowers_expectations`: `PLUGIN_ROOT = plugin_files_root("superpowers")`,
    `SKILLS_ROOT = PLUGIN_ROOT / "skills"`. `RESOURCES_ROOT` is deleted.
    `resource_files()` is scoped to `SKILLS_ROOT`, and `pack_files()` scans
    `PLUGIN_ROOT`. Keep the `PACK_ROOT` name as an alias of `PLUGIN_ROOT` until
    Task 7 renames the module.

- [ ] **Step 1: Write the failing tests** in `test_sources_filesystem_bundled.py`:
  - `test_engine_rules_come_from_content_core`: every
    `FileSystemArtifactSource(repo_root=tmp).list_rules()` rule with
    `source_package == "coding_agent_playbook"` has a `source_path` under
    `CORE_ROOT / "rules"`, and there are 12 of them.
  - `test_pack_names_resolve_to_content_plugins`: with
    `overlay_packages=["coding_agent_playbook.packs.superpowers"]`,
    `list_skills()` holds 15 skills attributed to that name, with `scripts_dir`
    under `catalog/plugins/superpowers/skills`.
  - `test_two_portion_namespace_overlay_still_resolves`. Make `nsov` a
    namespace package across two `tmp_path` portions on `sys.path`: portion a
    has `nsov/resources/rules/r.md` and portion b has
    `nsov/resources/skills/s1/SKILL.md`. Both `_resource_subdir("nsov","rules")`
    and `("nsov","skills")` resolve. Use `monkeypatch.syspath_prepend`.
  - `test_plugin_with_eval_tasks_and_prompts` (Review Focus 2). Monkeypatch
    `catalog._PACKAGE_DIR` to `tmp/src/coding_agent_playbook`. Build a
    tmp `catalog/` with `core/rules/`, `plugins/demo/eval_tasks/t1/task.toml`
    (copy a minimal valid shipped task.toml) and `plugins/demo/prompts/<its prompt>.md`.
    Expect `list_eval_tasks()` with `overlay_packages=["coding_agent_playbook.plugins.demo"]`
    to contain `t1` with that `source_package`. Expect `_infer_prompts_dir`
    to return `plugins/demo/prompts`.
  - `test_unusable_overlays_accepts_pack_names`:
    `unusable_overlays(["coding_agent_playbook.packs.superpowers", "coding_agent_playbook.plugins.superpowers"]) == []`.
    Also `unusable_overlays(["coding_agent_playbook.plugins.nope"])[0].reason`
    starts with `"no such bundled plugin"`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3: Do the `git mv`s.** Then check:
  - `git status` shows renames only;
  - `git ls-files -s content | awk '$1=="100755"' | wc -l` prints `10`;
  - `src/coding_agent_playbook/resources/` no longer exists;
  - each `packs/<n>/` keeps only `__init__.py`.
- [ ] **Step 4: Implement `_resource_subdir`'s bundled branch.** It must sit
  before and outside the `try`. The non-bundled body stays verbatim.
- [ ] **Step 5: Implement the bundled branch in `_unusable_reason`.** If
  `is_bundled_layer(name)` and `name != ENGINE_PACKAGE`, return `None` when
  `catalog_layer_root(name)` resolves, else `"no such bundled plugin"`. Bare
  parent names still take the import path in this task.
- [ ] **Step 6: Update `pyproject.toml`.** Make the spec's
  "Packaging and tooling" pyproject edits exactly:
  - `"catalog" = "coding_agent_playbook/_catalog"` under
    `[tool.hatch.build.targets.wheel.force-include]`;
  - `extend-exclude = ["catalog/plugins/superpowers", "catalog/plugins/python_design/**/*.md"]`;
  - `per-file-target-version = { "catalog/plugins/*/skills/*/scripts/*.py" = "py310" }`;
  - delete the three mypy `exclude` patterns and their comment block; drop the
    key if it ends up empty.
- [ ] **Step 7: Make the content path-text edits.** Then check that
  `git diff -M --stat catalog/` shows only those 11 files with line changes.
- [ ] **Step 8: Update the test roots listed above.** Then run
  `grep -rn "resources\" / \"skills\"\|/ \"resources\"" tests/packs tests/integration`.
  Expected: only third-party overlay fixtures remain.
- [ ] **Step 9: Run the full gate.** Expected: green.
  - Engine rules, prompts and tasks are discovered (Task 1's guards).
  - `tests/packs/python_design/test_pack.py` runs mypy on the scripts at their
    new paths.
- [ ] **Step 10:** Commit: `refactor: move bundled content to catalog/ and resolve it through catalog`.

---

### Task 7: Rename packs to bundled plugins

**Files:**
- Delete: `src/coding_agent_playbook/packs/` (all three `__init__.py`)
- Create: `catalog/plugins/superpowers/README.md` and
  `catalog/plugins/python_design/README.md`. Each carries its deleted
  docstring's prose with paths reworded and the enable line
  `overlays_enabled = ["coding_agent_playbook.plugins.<n>"]`. No URLs. The
  superpowers one has no `superpowers:<skill>`; the python_design one does not
  name its source plugin.
- Modify: `src/coding_agent_playbook/commands/_sync_preflight.py`:
  - drop `from coding_agent_playbook import packs`;
  - `_ENGINE_PACKAGE` comes from `catalog`;
  - in `_unusable_reason`, `is_plugin_namespace` comes first;
  - `bundled_packs` → `bundled_plugins`; `_pack_hint` → `_plugin_hint`;
    `_looks_like_pack` → `_looks_like_plugin`;
  - docstrings :3-12, :71, :75 and `report_unusable_overlays` wording say
    "overlay package or bundled plugin".
- Modify: `.pre-commit-hooks.yaml` comment block (wording only)
- Move: `tests/packs/` → `tests/plugins/` (`git mv`, keeping both `__init__.py`)
- Modify tests:
  - `tests/plugins/superpowers_expectations.py`: define
    `PLUGIN_NAME = "coding_agent_playbook.plugins.superpowers"`; drop the
    `PACK_ROOT` alias.
  - `tests/plugins/python_design/test_pack.py:33,35,106,112`
  - `tests/plugins/test_superpowers_pack.py:45-51`
  - `tests/plugins/test_superpowers_self_contained.py:108`
  - `tests/plugins/test_superpowers_sync.py:38`
  - `tests/cli/test_config_errors.py:22,24`
  - `tests/cli/test_check.py:15`
  - `tests/cli/test_validate_links.py:15,19`
  - `tests/cli/test_unusable_overlays.py:5,26-27,39,44,84-88,114-125,205,242,360-368`
  - `tests/unit/test_sync_preflight.py:12,18,43-55,67-83`
  - `tests/integration/test_resources_self_contained.py:48` (prefix
    `plugins/python_design/`; `README.md` replaces `__init__.py`)

**Interfaces:**
- Consumes: `catalog.bundled_plugins`, `is_plugin_namespace`,
  `ENGINE_PACKAGE`.
- Produces: `_sync_preflight.bundled_plugins`, re-exported from
  `catalog`. The `bundled_packs` name is removed.
- Produces: test constant `PLUGIN_NAME`, in
  `tests/plugins/superpowers_expectations.py`, with a sibling in `test_pack.py`.

- [ ] **Step 1: Write the failing tests.**
  - `test_plugin_namespace_reason`: for both bare names,
    `unusable_overlays([name])[0].reason` equals
    `"the bundled plugin namespace, not a plugin (bundled plugins: coding_agent_playbook.plugins.python_design, coding_agent_playbook.plugins.superpowers)"`.
  - `test_plugin_namespace_never_imported`: monkeypatch
    `_sync_preflight.importlib.import_module` to raise `AssertionError`. Both
    bare names still give the namespace reason.
  - `test_no_resources_reason_for_third_party`: parametrized over `json` and
    `os`. The reason is `_NO_RESOURCES`, with no hint.
  - `test_bundled_plugins_is_sorted_dotted_names` replaces
    `test_bundled_packs_lists_only_subpackages`. It is the tmp-root case from
    Task 3, run through the `_sync_preflight` re-export.
  - `test_superpowers_plugin_layout`: the only directory under `PLUGIN_ROOT` is
    `skills`. `{"LICENSE", "ATTRIBUTIONS.md", "README.md"}` are present, and
    `PLUGIN_NAME in bundled_plugins()`.
  - `test_init_refuses_unknown_bundled_plugin_in_local_file` (Review Focus 5).
    The local file has `overlays_enabled = ["coding_agent_playbook.plugins.nope"]`.
    `playbook init --non-interactive --name x --kind python-library` returns 2.
    stderr names `overlays_enabled in .coding-agent-playbook.local.toml` and
    `no such bundled plugin`. No `.coding-agent-playbook.toml` is created.
  - In `test_unusable_overlays.py`, `_PARENT` splits into
    `_NO_RES = "json"` (existing `_NO_RESOURCES` pins, without the hint) and
    `_NAMESPACE = "coding_agent_playbook.plugins"` (one validate case and one
    init case, pinning the namespace reason plus hint).
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Make the code, README and rename changes listed under Files.
  Switch every test importer to `tests.plugins.*`, `PLUGIN_NAME` and
  `bundled_plugins`. Tests that write consumer configs use `PLUGIN_NAME`.
  Exception: `tests/cli/test_init.py:410` (`_LOCAL_OVERRIDES`) keeps the
  literal old name and gains the comment
  `# alias regression: init checks the local list as written (SPEC v0.19)`.
- [ ] **Step 4:** Run `grep -rn "coding_agent_playbook\.packs\|tests\.packs\|bundled_packs\|PACK_NAME" src tests`.
  Expected hits:
  - `catalog.py` (`DEPRECATED_PACK_NAMESPACE`);
  - `test_init.py:410`;
  - deliberate alias tests only.
- [ ] **Step 5:** Run the full gate. Expected: green.
- [ ] **Step 6:** Commit: `refactor!: packs become bundled plugins (coding_agent_playbook.plugins.<name>)`.

---

### Task 8: Deprecated `packs.*` alias

**Files:**
- Modify: `src/coding_agent_playbook/config.py` (`Config`: new field and `__post_init__`)
- Modify: `src/coding_agent_playbook/config_entries.py:20-26` (comment: derived `compare=False` fields are exempt)
- Modify: `src/coding_agent_playbook/config_schema.py` (fix-it hint maps items through `canonical_overlay_name`)
- Modify: `src/coding_agent_playbook/orchestrator.py` (`SyncContext.from_repo`: print the warnings)
- Modify: `src/coding_agent_playbook/commands/init.py` (canonicalize `--overlays`; print the flag warning after preflight passes)
- Modify: `src/coding_agent_playbook/commands/_committed_config.py:35-40` (`ConfigRewrite` docstring: for a refresh, `config` is the canonicalized view of `table`)
- Test:
  - `tests/unit/test_config.py:276-303` (`_fields_left_at_default` skips `compare=False`) plus a new pin;
  - `tests/unit/test_config_enabled_keys.py` (hint);
  - `tests/cli/test_alias_packs.py` (new);
  - `tests/unit/test_committed_config.py` (refresh pin).

**Interfaces:**
- Consumes: `catalog.canonical_overlay_list`, `canonical_overlay_name`.
- Produces: `Config.deprecated_overlay_names: tuple[str, ...]`, declared as
  `field(default=(), init=False, compare=False, repr=False)`.
- Produces: `orchestrator._warn_deprecated_overlays(config: Config, state: FileSystemStateSource) -> None`.
  It writes to stderr and is called only from `SyncContext.from_repo`.

- [ ] **Step 1: Write the failing tests.**
  - `test_config_canonicalizes_deprecated_overlays` (in `test_config.py`):
    ```python
    c = Config.from_dict(
        {
            **_FULL,
            "overlays_enabled": ["coding_agent_playbook.packs.x", "coding_agent_playbook.plugins.x"],
        }
    )
    assert c.overlays_enabled == ["coding_agent_playbook.plugins.x", "coding_agent_playbook.plugins.x"]
    assert c.deprecated_overlay_names == ("coding_agent_playbook.packs.x",)
    assert "deprecated_overlay_names" not in c.to_dict()
    assert set(c.to_dict()) == CONFIG_MANAGED_KEYS
    assert dataclasses.replace(c, overlays_enabled=["a"]).deprecated_overlay_names == ()
    ```
  - `test_fixit_hint_recommends_canonical_name`: `[overlays] enabled = ["coding_agent_playbook.packs.superpowers"]`
    gives a `ConfigError` whose hint contains
    `coding_agent_playbook.plugins.superpowers` and not `.packs.`.
  - `tests/cli/test_alias_packs.py`. Use `write_consumer_repo` with
    `overlays=["coding_agent_playbook.packs.superpowers"]` and the hermetic
    git env from `tests/conftest.py`.
    - `test_sync_with_pack_name_warns_once_and_renders`: `main(["sync", ...])`
      returns 0. stderr has exactly one line:
      `warning: .coding-agent-playbook.toml: overlays_enabled: 'coding_agent_playbook.packs.superpowers' is deprecated; use 'coding_agent_playbook.plugins.superpowers'`.
      `.claude/skills/brainstorming/SKILL.md` exists.
    - `test_both_spellings_listed` (Review Focus 1): config lists both. Returns
      0, with exactly one warning line, and the skills are written.
    - `test_warning_names_local_file`: the local file sets the old name. The
      warning starts with `warning: .coding-agent-playbook.local.toml:`.
    - `test_typo_under_old_namespace` (Review Focus 4): with
      `coding_agent_playbook.packs.superpower`, `sync` returns 1. stderr holds
      the warning recommending `…plugins.superpower`, then
      `coding_agent_playbook.plugins.superpower: no such bundled plugin (bundled plugins: …)`.
    - `test_check_reports_canonical_overlay`: `check` prints
      `Overlays: coding_agent_playbook.plugins.superpowers`.
    - `test_init_overlays_flag_canonicalizes`: a first run and a re-run with
      `--overlays coding_agent_playbook.packs.superpowers` both write
      `overlays_enabled = ["coding_agent_playbook.plugins.superpowers"]`.
      stderr has exactly one `warning: --overlays: …` line and no
      `overlays_enabled` warning.
    - `test_check_refresh_keeps_deprecated_name`: `check --refresh` leaves the
      committed `overlays_enabled` equal to `["coding_agent_playbook.packs.superpowers"]`
      (compare `tomllib`-parsed values) and still warns.
  - `test_plan_detector_cache_refresh_keeps_deprecated_overlay` (in
    `test_committed_config.py`). It checks three things:
    `rewrite.table["overlays_enabled"]` keeps the old name;
    `rewrite.config.overlays_enabled` is canonical;
    `rewrite.config.deprecated_overlay_names` holds the old name.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement as the spec's "Bundled plugins and the `packs`
  alias" section says.
  - `_warn_deprecated_overlays` takes `<file>` from
    `"overlays_enabled" in state.load_local_overrides()`.
  - Printing happens only in `from_repo`, never in `Config` or `SyncContext.__init__`.
  - In `test_config.py`, `_fields_left_at_default` gets
    `if not spec.compare: continue` and a docstring line saying derived fields
    never count.
- [ ] **Step 4:** Run the full gate. Expected: green, and no existing test
  sees an unexpected `warning:` line (tests now use plugin names).
- [ ] **Step 5:** Commit: `feat: accept coding_agent_playbook.packs.* as a deprecated alias with a warning`.

---

### Task 9: Fail loudly when bundled content is missing

**Files:**
- Modify: `src/coding_agent_playbook/cli.py:265-270` (catch `CatalogMissingError`; extend the docstring)
- Modify: `src/coding_agent_playbook/commands/init.py:370-388` (call `catalog_root()` next to `_refuse_unusable_overlays`, before `_plan_config`)
- Test: `tests/unit/test_cli.py`, `tests/cli/test_init.py`

**Interfaces:**
- Consumes: `CatalogMissingError` and `catalog._PACKAGE_DIR`
  (Task 3).

- [ ] **Step 1: Write the failing tests.** Monkeypatch
  `coding_agent_playbook.catalog._PACKAGE_DIR` to
  `tmp_path / "src" / "coding_agent_playbook"` (empty). Build a configured
  repo with `make_synthetic_repo` (`tests/conftest.py:141`).
  - `test_sync_exits_2_when_catalog_missing`: `main(["sync", "--repo-root", repo])`
    returns 2. stderr equals the spec's missing-content error line with the two
    tried paths.
  - `test_eval_list_exits_2_when_catalog_missing`: the same for
    `["eval", "--list", "--repo-root", repo]`.
  - `test_init_writes_nothing_when_catalog_missing`: on an empty repo,
    `init --non-interactive --name x --kind python-library` returns 2, and the
    repo directory listing is unchanged.
- [ ] **Step 2:** Run them. Expected: FAIL (silent zero artifacts, or a
  traceback).
- [ ] **Step 3:** Implement.
  - `cli.main` adds `except CatalogMissingError as exc:` and prints
    exactly the spec string. Build the message from `exc.tried`.
  - In `init`, the call sits before `# Nothing is written above this line.`.
- [ ] **Step 4:** Run the full gate. Expected: green.
- [ ] **Step 5:** Commit: `feat: exit 2 with a clear error when the engine's bundled content is missing`.

---

### Task 10: Repository guards and the wheel-smoke CI job

**Files:**
- Create: `tests/integration/test_catalog_layout.py`
- Modify: `.github/workflows/ci.yml` (new `wheel-smoke` job)

**Interfaces:** none new.

- [ ] **Step 1: Write the tests** in `test_catalog_layout.py`:
  - `test_no_tracked_file_matches_gitignore`. Run
    `git ls-files -ci --exclude-standard` with `cwd=REPO_ROOT` and a 30 s
    timeout. Skip when git is missing or `REPO_ROOT/.git` is absent. Assert
    the output is empty. The failure message lists the paths and says
    `add a '!' negation to .gitignore instead of 'git add -f'`.
  - `test_plugin_dirs_follow_the_leaf_rule`: every directory under
    `PLUGINS_ROOT` has an `isidentifier()` name, does not start with `_` or `.`,
    and has at least one of `rules/`, `prompts/`, `skills/`, `eval_tasks/`.
  - `test_no_bundled_artifact_links_to_a_layer_root_file`. For every `*.md`
    under `CORE_ROOT/{rules,prompts}` and `PLUGINS_ROOT/*/skills`, parse links
    with `links.extract_markdown_links`. Assert that no relative target
    resolves to a file directly under `CORE_ROOT` or `PLUGINS_ROOT/<n>`.
  - `test_src_package_holds_no_content`. Under `src/coding_agent_playbook/`,
    no files match `*.md`, `*.md.j2`, `task.toml` or `SKILL.md*`, except
    `templates/precommit/config.yaml.j2` (acceptance 2).
  - `test_editable_checkout_resolves_repo_content`: skip if
    `(_PACKAGE_DIR / "_catalog").exists()`. Otherwise assert
    `catalog_root() == REPO_ROOT / "catalog"`.
- [ ] **Step 2:** Run them. Expected: PASS. These are guards over already-correct
  state. Prove each one bites by planting a violation locally (a non-identifier
  plugin dir, a link to `../../LICENSE`, a stray `.md` under `src/`), seeing it
  fail, then reverting.
- [ ] **Step 3: Add the `wheel-smoke` job** to `ci.yml` on `ubuntu-latest`,
  Python 3.12, using pip only. Its steps are the spec's five numbered
  `wheel-smoke` steps in order.
  - Step 2 of the job is a short inline `python -c` that compares the wheel's
    `coding_agent_playbook/_catalog/` names with `git ls-files catalog`.
  - Run every `playbook` call with `</dev/null` and a `timeout 120` prefix.
- [ ] **Step 4:** Validate the job locally by running the same shell lines in a
  scratch venv: `uv venv`, then `uv pip install pip build`. Expected: all
  asserts pass, with `23 eval tasks` printed.
- [ ] **Step 5:** Run the full gate. Expected: green.
- [ ] **Step 6:** Commit: `ci: wheel-smoke job and content layout guards`.

---

### Task 11: Docs

**Files:**
- Modify: `SPEC.md`, as listed in the spec's "Docs" section:
  - locations: §4.1, §5.1, §6.3, §6.5.2, §11.5.x, §13.2, §20.3;
  - preflight clauses at :140, :1479, :1534, :1649, :1749, :1794;
  - regenerate the sample outputs at :1534, :1751-1752 and :1777 by running
    the commands;
  - rescope §11.5.2 :1597;
  - §12.8 label rules; §16.4 `wheel-smoke`;
  - glossary: add "Bundled plugin (formerly pack)" and rename the existing
    entry to "OpenCode plugin";
  - new contracts (the warning line, exit 2);
  - v0.19 bump in four places.
- Modify: `tests/unit/test_docs_check_rubric_refactor.py:117-118`
  (`0.19 (draft)`, `End of SPEC.md v0.19`, add `### v0.19`)
- Modify: `README.md`:
  - paths at :310 and :342;
  - the preflight passage at :283-294;
  - a new "Editing content" section;
  - a Mermaid overview of `catalog/` vs `src/`.
- Modify: `MIGRATION.md` (new v0.19 section, with every bullet from the spec's
  Docs list)
- Create: `catalog/README.md`. Cover where each kind lives, how to add a rule,
  prompt, eval task, skill or bundled plugin (with the leaf rule), and the four
  gate commands. Any python code block in it must pass `ruff format --check`.
- Modify: remaining docstrings that mention `resources/` or packs for the
  engine's own content. Find them with
  `grep -rn "resources/\|\bpacks\?\b" src/coding_agent_playbook --include='*.py'`.
  Overlay-contract mentions stay.

**Interfaces:** none.

- [ ] **Step 1:** Update the version pins in `test_docs_check_rubric_refactor.py`.
  Run it. Expected: FAIL.
- [ ] **Step 2:** Edit SPEC.md. Run the pin test. Expected: PASS.
- [ ] **Step 3:** Edit README.md and MIGRATION.md, create `catalog/README.md`,
  and sweep the docstrings.
- [ ] **Step 4:** Run `grep -n "src/coding_agent_playbook/resources\|packs/<\|coding_agent_playbook.packs" README.md SPEC.md MIGRATION.md`.
  Expected: hits only in the changelog history, the alias text and MIGRATION's
  rename section.
- [ ] **Step 5:** Run the full gate. Expected: green (`ruff format --check .`
  covers the new markdown).
- [ ] **Step 6:** Commit: `docs: SPEC v0.19, README, MIGRATION and catalog/README for catalog/ and bundled plugins`.

---

### Task 12: Acceptance verification

**Files:** none committed, unless a check finds a defect. A defect is fixed in
the task that owns it, with a regression test.

- [ ] **Step 1:** Run the full CI gate cache-free, with no optional extras, in
  a fresh scratch venv: `uv venv`, `uv pip install -e ".[dev]"`, then the gate
  with `ruff --no-cache` and `pytest -p no:cacheprovider`. Expected: green,
  coverage at least 80%.
- [ ] **Step 2: Acceptance 3.**
  1. Build with `uv build -o <scratch>/dist-new`.
  2. Map the baseline wheel's 239 content entries with the spec's mapping
     table.
  3. Compare sha256 and mode.

  Expected:
  - all identical, except the 10 `task.toml` files and the superpowers
    `ATTRIBUTIONS.md`, each differing only by the named substring;
  - 10 executables;
  - exactly 3 added files (the READMEs);
  - the 3 `__init__.py` files gone.
- [ ] **Step 3: Acceptance 4 (output parity).**
  1. Copy `parity-baseline/repo` minus the generated output. Keep the committed
     config and the local config.
  2. Run `playbook sync </dev/null` once as-is (old names), then again after
     `sed -i '' 's/coding_agent_playbook\.packs\./coding_agent_playbook.plugins./g' .coding-agent-playbook*.toml`.
  3. Diff the `manifest.py` output against `parity-baseline/manifest.txt`,
     excluding `.coding-agent-playbook.toml`, `.coding-agent-playbook.local.toml`
     and the masked `rendered_at` line.

  Expected: no other differences.
- [ ] **Step 4: Acceptance 5.** In a scratch copy of the repo, `mkdir -p catalog/plugins/demo/skills/hello`
  and add a minimal `SKILL.md`. Expected:
  `playbook init --non-interactive --name x --kind python-library --overlays coding_agent_playbook.plugins.demo`
  writes `.claude/skills/hello/SKILL.md`.
- [ ] **Step 5: Acceptance 6.** Run `git log --follow --oneline catalog/core/rules/always/10-python-house-style.md`.
  Expected: it shows commits from before this branch.
- [ ] **Step 6:** Dispatch the whole-branch review (`superpowers:requesting-code-review`)
  against the spec and this plan. Fix confirmed findings in their owning
  tasks' files, with regression tests.
