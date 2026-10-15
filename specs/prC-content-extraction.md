# PR C — Extract bundled content to `content/`; packs become bundled plugins

Status: approved design (2026-10-15), revised after an adversarial review
against the code. Moves every rule, prompt, eval task and bundled skill out of
the Python package into a top-level `content/` tree of the same repository. It
also renames the opt-in "packs" to "bundled plugins"; old names keep working
as a deprecated alias.

## Problem

Content (rules, prompts, eval tasks, skills) and engine logic share
`src/coding_agent_playbook/`. A contributor who only writes a rule or a skill
has to navigate the Python package, and every bundled pack needs a Python
subpackage (`packs/<name>/__init__.py`) just to exist. The goal is that content
maintainers work in one place and never touch the logic layer.

## Scope (locked with the user)

- **One wheel.** `content/` is a source folder only. Hatch copies it into the
  wheel at build time, so `pip install coding-agent-playbook` behaves exactly as
  today. There is no separate content distribution.
- **Layout.** `content/core/` holds the engine built-ins and
  `content/plugins/<name>/` holds the opt-in bundled plugins. The contributor
  guide is `content/README.md`.
- **Rename packs to bundled plugins** in code, config names, tests and docs.
  - The new config name is `coding_agent_playbook.plugins.<name>`.
  - `coding_agent_playbook.packs.<name>` keeps working, with a deprecation
    warning.
  - Exception: *content* files keep their current wording and only change path
    text (see "Content edits").
- **Bundled plugins are pure content.** There is no Python file per plugin.
  Adding `content/plugins/<name>/` is all it takes to ship a new plugin.
- **The pre-commit template stays in `src/`.** It is engine wiring, not playbook
  content: its hook ids are duplicated in `commands/_precommit_merge.py`.
- **The overlay contract is unchanged.** Third-party overlay packages still ship
  `<pkg>/resources/{rules,prompts,skills,eval_tasks}`, resolved exactly as today.

**Terminology.** "Plugin" already means three other things here: an OpenCode
plugin (SPEC glossary), an upstream Claude Code plugin (where superpowers and
python_design came from), and an entry-point extension (evaluator registries).
Prose therefore always says **bundled plugin** for ours. The SPEC glossary
gains a "Bundled plugin (formerly pack)" entry, and the existing glossary entry
becomes "OpenCode plugin".

## Target layout

Repository:

```
content/                         everything content maintainers edit
├── README.md                    contributor guide
├── core/                        was src/coding_agent_playbook/resources/ (minus precommit/)
│   ├── ATTRIBUTIONS.md
│   ├── rules/{always,languages/python,frameworks,ml}/
│   ├── prompts/
│   └── eval_tasks/{ATTRIBUTIONS.md,<task-id>/{task.toml,setup/,solution/[negatives/]}}
└── plugins/                     was src/coding_agent_playbook/packs/<name>/
    ├── superpowers/{README.md,LICENSE,ATTRIBUTIONS.md,skills/<skill>/…}
    └── python_design/{README.md,ATTRIBUTIONS.md,skills/<skill>/…}
src/coding_agent_playbook/
├── bundled_content.py           new: the only code that knows where content/ is
├── templates/precommit/config.yaml.j2   was resources/precommit/config.yaml.j2
└── …                            packs/ removed
tests/plugins/                   was tests/packs/ (with its __init__.py files)
```

Each plugin's `README.md` carries what the pack's `__init__.py` docstring says
today: what it is and how to enable it. These READMEs are scanned by the
existing self-containment gates, so they must contain no URL. The superpowers
README must contain no `superpowers:<skill>` reference, and the python_design
README must not name its source plugin. `README.md`, `LICENSE` and
`ATTRIBUTIONS.md` sit at a layer root, outside every kind directory, so no
artifact walk picks them up.

Installed wheel (internal; not a user-facing contract):

```
coding_agent_playbook/_content/{README.md,core/…,plugins/<name>/…}
coding_agent_playbook/templates/precommit/config.yaml.j2
```

The MIT `LICENSE` still ships inside the package, not in `dist-info`. Users
who need it (for example Continue-only users) find it in any synced
`references/LICENSE`, which stays byte-identical to the plugin `LICENSE`.

**Name constraints** (from the coupling map). The top-level folder must not be
any of:
- `resources/` or `playbook/`, which path logic matches;
- a root-level `skills/`, `prompts/`, `rules/` or `references/` (adapter
  output);
- a gitignored harness dir;
- an unanchored-ignored name such as `build/` or `lib/`.

`content/` is none of these.

## Components

### `bundled_content.py` (new)

This is the single place that locates the engine's own content. It is a leaf
module that imports nothing from the engine, so `config.py` and
`config_schema.py` can import it.

Constants:

| Name | Value |
| --- | --- |
| `ENGINE_PACKAGE` | `"coding_agent_playbook"` |
| `PLUGIN_NAMESPACE` | `"coding_agent_playbook.plugins"` |
| `DEPRECATED_PACK_NAMESPACE` | `"coding_agent_playbook.packs"` |
| `PACKAGED_CONTENT_DIRNAME` | `"_content"` (inside the installed package) |
| `CHECKOUT_CONTENT_DIRNAME` | `"content"` (at the repo root) |
| `_PACKAGE_DIR` | the package directory; the one module-level seam end-to-end tests may monkeypatch, read at call time |

`BundledContentMissingError(RuntimeError)` carries every path that was tried.

Functions:

- `bundled_content_root(package_dir: Path | None = None) -> Path`. `package_dir`
  defaults to `_PACKAGE_DIR`.
  1. **Installed wheel:** return `<package_dir>/_content` if
     `<package_dir>/_content/core` is a directory.
  2. **Source checkout:** return `<package_dir>/../../content` if
     `package_dir.parent.name == "src"` and `<repo>/content/core` is a
     directory.
  3. Otherwise raise `BundledContentMissingError`, naming both paths.

  Rule 1 must check for `core/` too. Otherwise a wheel with a mis-scoped
  force-include would load zero engine artifacts silently.
- `bundled_plugins(content_root: Path | None = None) -> list[str]`. Sorted dotted
  names (`coding_agent_playbook.plugins.<dir>`), from `iterdir()` on
  `<root>/plugins`. It keeps only directories whose name `isidentifier()` and
  does not start with `.` or `_`. `iterdir()` returns the on-disk spelling, so
  later comparisons stay exact on case-insensitive volumes.
- `canonical_overlay_name(name: str) -> str`. Rewrites
  `coding_agent_playbook.packs.<rest>` to `coding_agent_playbook.plugins.<rest>`
  when `<rest>` is non-empty. The prefix includes the dot, so the bare
  `coding_agent_playbook.packs` comes back unchanged. Every other name is
  returned unchanged.
- `canonical_overlay_list(names) -> tuple[list[str], tuple[str, ...]]`. Returns
  the canonical names in the same order, with no dedup, plus the deprecated
  names it rewrote.
  - There is no dedup because listing the same overlay twice behaves today
    exactly as it will after canonicalization: it is walked twice and the later
    walk wins.
  - The deprecation warning tells the user to fix the list.
- `is_plugin_namespace(name: str) -> bool`. True only for the two bare names
  `PLUGIN_NAMESPACE` and `DEPRECATED_PACK_NAMESPACE`.
- `is_bundled_layer(name: str) -> bool`. True for `ENGINE_PACKAGE`, and for any
  name starting with `PLUGIN_NAMESPACE + "."` or `DEPRECATED_PACK_NAMESPACE + "."`.
- `bundled_layer_root(name: str, *, content_root: Path | None = None) -> Path | None`.
  1. Returns `<root>/core` for the engine.
  2. For any other name, canonicalizes it first, so both namespaces resolve.
  3. Returns `<root>/plugins/<leaf>` only when the canonical name is exactly an
     entry of `bundled_plugins(content_root)`. The leaf is the full remainder
     after the prefix.
  4. Returns `None` for anything else: an empty leaf, `..`, `/`, nested dots,
     the wrong case, or `__pycache__`.

  It never joins unchecked config text onto a path. If the content root itself
  is missing, it raises `BundledContentMissingError`.

### `sources/filesystem.py`

`_resource_subdir(package, subdir)` keeps its name, signature and `None`
contract, and branches:

- **Bundled layer:** return `bundled_layer_root(package) / subdir` if that is a
  directory. This branch sits *outside* the existing `except Exception`
  guard, so `BundledContentMissingError` propagates. That is the one exception
  to the never-raise contract.
- **Every other package:** keep today's body verbatim. That is the single
  two-segment `resources.files(package).joinpath("resources", subdir)` call, the
  `except Exception` guard, and the `Path(str(...))` conversion only after the
  full join. Splitting the join into two steps would silently drop a namespace
  overlay whose `resources/` spans two portions.

The walks, the `source_package` attribution and the layer order are unchanged.
The comment at `filesystem.py:72-75` claims `MultiplexedPath` is always safe.
It is corrected to describe the real limit: a kind directory that spans
portions is not supported, and this is pre-existing.

### Bundled plugins and the `packs` alias

**Canonicalization (`Config.__post_init__`).**
- `Config.__post_init__` runs `canonical_overlay_list`. It rewrites
  `overlays_enabled` and sets a new field,
  `deprecated_overlay_names: tuple[str, ...] = field(default=(), init=False, compare=False, repr=False)`.
- Because this is `__post_init__`, `from_dict`, direct construction (`init`'s
  `_fresh_config`) and `dataclasses.replace` all agree. The field can never go
  stale.
- `to_dict` never writes the field, and `Config` itself never prints.

**The warning (`SyncContext.from_repo`).**
- `SyncContext.from_repo` prints exactly one stderr line per deprecated name:
  `warning: <file>: overlays_enabled: 'coding_agent_playbook.packs.<leaf>' is deprecated; use 'coding_agent_playbook.plugins.<leaf>'`.
- `<file>` is `.coding-agent-playbook.local.toml` when that file has an
  `overlays_enabled` key (lists replace whole in the §7.2 merge). Otherwise it
  is `.coding-agent-playbook.toml`.
- Only `from_repo` prints, not `SyncContext(...)`, so tests that build one
  directly stay silent.
- Commands that read `overlays_enabled` (sync, check, validate, render, eval,
  and init's final sync) all go through `from_repo`.
- The warning is a print, not `warnings.warn`: CLI users never see
  `DeprecationWarning`, and pytest runs with `filterwarnings = error`.
- A typo under the old namespace still warns, recommending the canonical
  spelling. The next line is then the preflight error for that canonical name.

**`init --overlays`.**
- `init --overlays` canonicalizes its arguments with the same helper. It prints
  `warning: --overlays: '<old>' is deprecated; use '<new>'` once per deprecated
  argument, after the preflight passes.
- `init` writes the canonical names, on a first run and on a re-run, so a
  re-run is the migration path for the committed file.
- `init` does not warn about the local file's list. Its final sync's
  `from_repo` already does.

**What rewrites the config.**
- `check --refresh` keeps writing every key except `[detector_cache]` exactly as
  parsed (SPEC §12.5 unchanged), so a deprecated name in the committed file
  stays there. For a refresh, `ConfigRewrite.config` is the canonicalized view
  of `ConfigRewrite.table`; its docstring says so.
- `sync` never rewrites the config, and no command rewrites
  `.coding-agent-playbook.local.toml`. The warning is the migration nudge until
  the user edits the file or re-runs `init --overlays …`.

**What stays the same.**
- The lockfile stores only paths and hashes, so canonicalization causes no
  `sync --check` drift.
- Diagnostics (collisions, `check`, `render`, `eval` labels) print the
  canonical name.

**Smaller changes.**
- `config_schema.py` maps each item through `canonical_overlay_name` in the
  fix-it hint for a misspelled `[overlays] enabled`, so the hint never
  recommends the deprecated name.
- `src/coding_agent_playbook/packs/` is deleted, including the `PACK_NAME`
  constants, with no import shim. SPEC documented `PACK_NAME`, so MIGRATION.md
  lists the removal.

### Sync preflight (`commands/_sync_preflight.py`)

`_unusable_reason(name)` classifies names in this order, without importing
anything for the first two:

1. `is_plugin_namespace(name)`: return the fixed reason
   `the bundled plugin namespace, not a plugin`. Because the namespace is never
   imported, a leftover `src/coding_agent_playbook/packs/` holding only
   gitignored `__pycache__/` cannot change the result.
2. `is_bundled_layer(name)` (except the engine): the name is usable if
   `bundled_layer_root(name)` is not `None`. Otherwise the reason is
   `no such bundled plugin`.
3. Every other name keeps today's import and `resources/` check, unchanged. It
   still reports `_NO_RESOURCES` for third-party packages.

Hints and wording:
- `bundled_packs()` becomes `bundled_plugins()`, imported from
  `bundled_content`. The hint becomes ` (bundled plugins: …)`. It is still
  appended for names under the engine package or close to a plugin's leaf
  (`_looks_like_pack` becomes `_looks_like_plugin`).
- `_ENGINE_PACKAGE` comes from `bundled_content.ENGINE_PACKAGE`.
- User-facing text that calls every `overlays_enabled` entry an installable
  package says "overlay package or bundled plugin" instead. This covers
  `report_unusable_overlays`, the module docstring and `.pre-commit-hooks.yaml`
  comments.

### Eval path logic

**`evals/prompting.py:_infer_prompts_dir(task_toml)`.**
- It stops searching for a `resources` path segment. When
  `task_toml.parent.parent.name == "eval_tasks"`, it returns
  `task_toml.parents[2] / "prompts"`. Otherwise it returns `None`.
- It does not call `resolve()`, so symlinks behave.
- Behaviour change: a repo-local task under `playbook/eval_tasks/` now finds
  `playbook/prompts/`. Today it never finds a prompt. This is recorded in the
  SPEC v0.19 changelog.

**`commands/eval.py:_display_source_path(task)`.** The label is built from the
layer, not by searching the path. `<dir>` is always
`task.source_path.parent.name`, never `task.id`, which nothing ties to the
directory.
- Bundled layers: `"<source_package>/eval_tasks/<dir>/"`.
- Third-party overlays: `"<source_package>/resources/eval_tasks/<dir>/"`. This
  is still a real package-relative path, so it is unchanged.
- Repo-local: `"playbook/eval_tasks/<dir>/"`.

### `init` and the pre-commit template

- The template moves to `src/coding_agent_playbook/templates/precommit/config.yaml.j2`.
- A named accessor, `commands/init.py:precommit_template_dir() -> Path`,
  returns `Path(str(resources.files(ENGINE_PACKAGE) / "templates" / "precommit"))`.
  It raises an explicit error naming the expected path when the directory or
  `config.yaml.j2` is missing. This replaces `assert precommit_dir is not None`,
  which `-O` strips.
- `_resource_subdir(ENGINE_PACKAGE, "precommit")` now returns `None` by design.
- `init` calls `bundled_content_root()` in its preflight, next to
  `_refuse_unusable_overlays` and before anything is written. A broken install
  then never leaves a half-initialized repo.

### Loud failure

`cli.main` catches `BundledContentMissingError` and exits 2, printing this to
stderr:

`error: the engine's bundled content was not found (looked in <a>, <b>); reinstall coding-agent-playbook`

Today a lookup miss silently produces zero engine artifacts.

## Packaging and tooling

**`pyproject.toml`.**
- `[tool.hatch.build.targets.wheel.force-include]` gains
  `"content" = "coding_agent_playbook/_content"`.
- The sdist needs no change: hatch includes every non-ignored file, and
  `content/` is not ignored.
- ruff `extend-exclude` is repointed to `content/plugins/superpowers` and
  `content/plugins/python_design/**/*.md`.
- `per-file-target-version` is repointed to
  `content/plugins/*/skills/*/scripts/*.py`.
- The mypy `exclude` patterns for `resources/eval_tasks/…` and
  `packs/…/scripts|references` are deleted, because content is outside `files`.
  `content/` is not added to mypy `files`, because fixture module names collide.

**Force-include ignores `.gitignore` in both directions.**
- It ships untracked ignored junk from a dirty tree.
- It ships tracked files that match `.gitignore`, which the sdist drops.

Releases are therefore built from the sdist: plain `uv build` or
`python -m build`, never `--wheel`. git and pre-commit installs always build
from the tree, so a new pytest guard asserts that
`git ls-files -ci --exclude-standard` is empty. It is skipped outside a git
checkout. Its failure names each path and suggests a `!` negation in
`.gitignore` instead of `git add -f`.

**Editable installs.** hatch also copies the force-included tree into a shadow
`site-packages/coding_agent_playbook/_content/`. Nothing ever imports it,
because the package resolves from `src/` and `bundled_content_root` looks only
under the package directory. This is accepted.

**CI `wheel-smoke` job.** A new job in `ci.yml`, using pip only. In order:
1. `python -m pip install build && python -m build`. This builds the sdist,
   then a wheel from it.
2. Assert that the wheel's `coding_agent_playbook/_content/**` entries equal
   `git ls-files content`, mapped to `_content/`.
3. Install the wheel non-editable into a fresh venv and run `playbook --version`.
4. In an empty scratch directory outside the checkout, run:
   `playbook init --non-interactive --name smoke --kind python-library --overlays coding_agent_playbook.plugins.superpowers,coding_agent_playbook.plugins.python_design </dev/null`.
   Assert exit 0, no `warning:` line, and both
   `.claude/skills/brainstorming/SKILL.md` and
   `.claude/skills/python-design-review/SKILL.md` exist.
5. In that same directory, run `playbook eval --list </dev/null`. Assert the
   output contains `23 eval tasks`. That count comes from core content only.

**File moves.** All moves use `git mv`, so history follows and the 10
executable scripts stay `100755`.

## Content edits (path text only)

Content files keep their wording, and only path text changes.
- The 10 `find-injected-vuln-*/task.toml` descriptions change
  `See resources/eval_tasks/ATTRIBUTIONS.md.` to `See eval_tasks/ATTRIBUTIONS.md.`
- `content/plugins/superpowers/ATTRIBUTIONS.md` line 3 says `skills/` instead of
  `resources/skills/`. The python_design ATTRIBUTIONS.md has no path text and
  is not edited.
- Both ATTRIBUTIONS.md files keep "pack" and "the plugin" as they are. There,
  "plugin" correctly means the upstream Claude Code plugin.
- The engine-authored additions inside the vendored superpowers skills keep
  saying "pack". Output parity requires it. These are
  `diagnosing-superpowers/references/prompts/skill-timeline.md` and
  `references/templates/case.md`.
- Vendored upstream superpowers files stay byte-identical, including all 15
  `references/LICENSE` copies, which must still match the plugin `LICENSE`.

## Tests

### Before any move

Add "found at least one" assertions wherever empty content currently passes
silently:
- the `test_shipped_task_gates` parametrization;
- the `test_resources_self_contained` rglob;
- `tests/packs/python_design/test_pack.py:89`;
- the engine link gate in `test_validate_links.py`.

### Shared paths

`tests/_content.py` (`tests/` is already a package) is anchored on the
checkout, not on the production resolver, so the existing "resolver agrees
with the tree" pins stay meaningful:
- `REPO_CONTENT = Path(__file__).resolve().parents[1] / "content"`;
- `CORE_ROOT`, `PLUGINS_ROOT` and `plugin_root(name)` built from it;
- `PRECOMMIT_TEMPLATE_DIR`, computed with
  `resources.files(ENGINE_PACKAGE) / "templates" / "precommit"`.

One test asserts `bundled_content_root() == REPO_CONTENT`. It is skipped when
`<pkg>/_content` exists.

The 12 modules that hard-code `parents[N] / "src" / "coding_agent_playbook" / "resources"`
switch to this helper.

### Rename

`tests/packs/` becomes `tests/plugins/` via `git mv`, keeping its
`__init__.py` files. `PLUGIN_NAME` is defined once in
`tests/plugins/superpowers_expectations.py`, and `test_pack.py` defines its own
the same way. Every importer of `coding_agent_playbook.packs.*`,
`tests.packs.*` or `bundled_packs` switches over:
- `tests/cli/test_config_errors.py:22,24`
- `tests/cli/test_check.py:15`
- `tests/cli/test_validate_links.py:15,19`
- `tests/cli/test_unusable_overlays.py:26-27`
- `tests/unit/test_sync_preflight.py:12,18`
- `tests/packs/test_superpowers_sync.py:38`
- `tests/packs/python_design/test_pack.py:33,35,106`

### Pin replacements

**Superpowers expectations.**
- `PLUGIN_ROOT = plugin_root("superpowers")` and `SKILLS_ROOT = PLUGIN_ROOT / "skills"`.
  `RESOURCES_ROOT` is deleted.
- `resource_files()`, and with it the upstream-coupling regex scan, stays scoped
  to `SKILLS_ROOT`. That regex contains `plugins/superpowers` and
  `obra/superpowers`, both of which now appear outside `skills/`.
  `pack_files()` still scans the whole plugin root.
- `test_superpowers_self_contained.py:108` expects
  `{"LICENSE", "ATTRIBUTIONS.md", "README.md"}`.
- `test_superpowers_pack.py:45-51` drops `import_module` and pins
  `PLUGIN_NAME in bundled_plugins()`. The only directory under `PLUGIN_ROOT` is
  `skills`.

**python_design `test_pack.py`.**
- `plugin_root("python_design") / "skills"`.
- `:106` pins the `plugins` name.
- `:112` asserts the only directory under the plugin root is `skills`.

**`test_resources_self_contained.py`.**
- The prefix becomes `plugins/python_design/`, and `resources/skills/` becomes
  `skills/`.
- `"precommit/"` is dropped from the content prefixes. `__init__.py` becomes
  `README.md`.
- An explicit `ScanTarget` for `templates/precommit/config.yaml.j2` uses the
  full URL and marker policy, so the template stays scanned.
- The docstring paths are updated.

**`test_precommit_template.py`.** Uses `precommit_template_dir()`.

**Preflight pins.**
- In `test_sync_preflight.py:43-48`, `coding_agent_playbook.packs` leaves the
  `_NO_RESOURCES` parametrization; `json` and `os` remain.
- A new test pins the namespace reason for both bare names. It also
  monkeypatches `importlib.import_module` to raise, which proves neither name
  is imported.
- The hint pins change to `(bundled plugins: …)`: `test_sync_preflight.py:55,67-72`
  and `test_unusable_overlays.py:44`.
- `test_bundled_packs_lists_only_subpackages` becomes a `tmp_path` test of
  `bundled_plugins(content_root=…)`. It checks that a stray file, a `.hidden`
  dir and `__pycache__` are excluded, and that a new `plugins/new_one/` dir is
  listed and resolves (acceptance 5).

**`test_unusable_overlays.py`.**
- `_PARENT` splits in two:
  - `_NO_RES = "json"` covers the `_NO_RESOURCES` path at `:84-88, :114-125, :205, :242, :360-368`,
    with no hint.
  - `_NAMESPACE = "coding_agent_playbook.plugins"` pins the namespace reason
    plus the hint in at least one validate case and one init case.
- The module docstring and `_sync_preflight.py:71` stop using the engine parent
  as their example.

**`test_eval.py`.**
- `:348` becomes `coding_agent_playbook/eval_tasks/task-a/`.
- `:366` (third-party overlay) is unchanged.
- The fallback test at `:369-401` becomes "the label depends only on the layer
  kind, `source_package` and the directory name".
- A new case has `task.id` differ from the directory name.

**Config and alias pins.**
- In `test_config.py`, `_fields_left_at_default` skips `compare=False` fields,
  and its docstring calls them derived diagnostics.
- A new positive pin:
  `Config.from_dict({..._FULL, "overlays_enabled": ["coding_agent_playbook.packs.x", "coding_agent_playbook.plugins.x"]})`
  gives canonical `overlays_enabled` (both entries, in order),
  `deprecated_overlay_names == ("coding_agent_playbook.packs.x",)`, and
  `set(to_dict()) == CONFIG_MANAGED_KEYS`.
- `test_init.py:410` (`_LOCAL_OVERRIDES`) stays on the old name and gains a
  comment: it is the alias regression test for init's local-list check.

### New tests

- **Resolver:**
  - the packaged root wins;
  - the checkout fallback works;
  - the wheel case without `core/` raises;
  - a missing root raises and names both paths;
  - plugin names that are wrong case, an empty leaf, `..`, `../core`, nested
    dots, `/tmp`, or `__pycache__` give `None`;
  - both spellings resolve to the same plugin.
- **A content gate:** every directory under `content/plugins/` passes the leaf
  rule and has at least one kind subdirectory.
- **Two-portion namespace overlay:** `resources/rules` in one portion and
  `resources/skills` in the other both resolve and are attributed to the
  overlay.
- **Alias end to end:**
  - `sync` and `check` on an old-name committed config print exactly one
    warning line naming the file;
  - `init --overlays <old>` on a first run and on a re-run writes the canonical
    name and prints one `--overlays` warning;
  - `check --refresh` keeps a deprecated name as written (compare parsed values)
    while the `Overlays:` line shows the canonical name;
  - `init` with a deprecated name only in the local file exits 0.
- **Loud failure:** `main(["sync", …])` and `main(["eval", "--list", …])` on a
  configured synthetic repo, with `_PACKAGE_DIR` pointed at an empty
  `tmp_path`, return 2 with the exact stderr line. `init` exits 2 before
  writing anything.
- **Prompts dir:** `_infer_prompts_dir` for bundled, overlay `resources/` and
  repo-local layers, plus a non-task path.
- **Templates:** the `precommit_template_dir()` error, and the gitignore guard
  above.
- **Link containment:** no bundled artifact links to a layer-root file
  (`README.md`, `LICENSE`, `ATTRIBUTIONS.md`). Those ship in the wheel but are
  never synced, so such a link would break in consumer repos. Moving plugin
  root files into the link gate's containment root makes these links
  structurally possible, so this pin replaces the protection the old layout
  gave by accident.

### Output parity

The baseline was captured before any change, from commit `cad7577`.
- **Repo:** a scratch consumer repo with every adapter and both packs enabled,
  built by `playbook init --non-interactive`.
- **Result:** 476 files, 40 of them `0755`.
- **Manifest:** (path, sha256, mode) for every file except `.git/`, saved in
  the session scratchpad, outside the repo.

After the change, the same procedure runs twice: once reusing the baseline
config with the old pack names, and once with `packs.` replaced by `plugins.`
through sed. The `[engine] version` and adapter set stay fixed, and init is
not re-run. Every manifest line must match except:
- `.coding-agent-playbook.toml`, which is input and differs by the names;
- the `rendered_at` line of the lockfile, which is a wall-clock timestamp.

The overlay-contract fixtures (third-party `<pkg>/resources/…`) pass
unmodified.

## Docs

**`SPEC.md`.**
- Every passage that says where the engine's own content lives: §4.1 diagram,
  §5.1 tree, §6.3, the §6.5.2 tree, §11.5 packs → bundled plugins, the
  §11.5.x ruff and mypy paths and the "next to `__init__.py`" wording, §13.2
  template path, §20.3 and the examples.
- Preflight passages are not exempt as "overlay contract" (§4.2 step 1 :140,
  §11.1 :1479, §11.5 :1534, §12.1 :1649, §12.4 :1749, §12.6 :1794). Each gains
  a clause: a bundled-plugin name is checked against `content/plugins/<leaf>/`
  and never imported.
- The sample outputs at :1534, :1751-1752 and :1777 are regenerated with the
  new reason, hint and warning lines.
- §11.5.2 :1597 is rescoped to skill files: "the name of the source Claude Code
  plugin".
- §12.8 label rules; §16.4 gets the `wheel-smoke` job.
- New contracts get a SPEC home: the warning line and the exit-2 message.
- The glossary entry (see Terminology).
- **Version bump to v0.19** in four places: the Version and Last updated rows,
  a top changelog bullet, a `### v0.19` appendix entry and the footer. The
  pins in `tests/unit/test_docs_check_rubric_refactor.py` are updated, and a
  `### v0.19` assert is added.

**`README.md`.**
- Paths at :310 and :342.
- The preflight passage at :283-294, with the new reason and hint text.
- A short "Editing content" section.
- A Mermaid overview showing `content/` vs `src/`.

**`MIGRATION.md`, new v0.19 section.**
- The `packs` → `plugins` rename and the alias.
- The alias stays through 0.x; its removal will be announced in MIGRATION.md
  one release ahead.
- A deprecated name stays in the committed file until `init --overlays …` is
  re-run or the file is edited. The local file must be edited by hand.
- `coding_agent_playbook.packs[.<name>]` modules and `PACK_NAME` are removed
  with no shim. Use the dotted string instead.
- The new preflight reason and hint texts.
- The bundled `eval --show` label.
- The new warning line.

**`content/README.md` (new).**
- Where each kind lives.
- How to add a rule, prompt, eval task, skill or bundled plugin, including the
  leaf naming rule.
- The four CI gate commands. It names four rather than "one command" because
  local pre-commit only ruff-formats Python, while CI's
  `ruff format --check .` also formats code blocks in markdown, so the guide's
  own Python blocks must be ruff-formatted.

**Module docstrings and messages** that mention `resources/` or packs, as listed
in the coupling map.

## Acceptance criteria

1. **CI gate.** The gate passes, cache-free and without optional extras:
   `ruff check .`, `ruff format --check .`, `mypy`, and `pytest -q` (coverage at
   least 80%). The `wheel-smoke` job passes too.
2. **Package is logic only.** `src/coding_agent_playbook/` contains no `.md`,
   `.md.j2`, `task.toml` or skill files, except
   `templates/precommit/config.yaml.j2` and `py.typed`.
3. **Wheel content.** The baseline wheel's 239 content files map 1:1. These are
   the 236 files under `resources/` and `packs/<n>/resources/`, plus
   `packs/superpowers/{LICENSE,ATTRIBUTIONS.md}` and
   `packs/python_design/ATTRIBUTIONS.md`.
   - **Mapping:**
     - `resources/X` → `_content/core/X`
     - `resources/precommit/config.yaml.j2` → `templates/precommit/config.yaml.j2`
     - `packs/<n>/resources/skills/X` → `_content/plugins/<n>/skills/X`
     - `packs/<n>/{LICENSE,ATTRIBUTIONS.md}` → `_content/plugins/<n>/…`
   - **Bytes:** every mapped file is byte-identical, except the 10
     `find-injected-vuln-*/task.toml` files and the superpowers
     `ATTRIBUTIONS.md`. Each of those differs only by the substring named in
     "Content edits".
   - **Modes:** the same 10 files are `0755`.
   - **Additions and removals:** exactly 3 files are added:
     `_content/README.md` and two `plugins/<n>/README.md`. The 3
     `packs/**/__init__.py` files are removed. Nothing else is added or dropped.
4. **Output parity.** Holds for both old and new plugin names (see Tests).
5. **New plugins need no code.** Adding a directory under
   `content/plugins/<name>/skills/` makes `coding_agent_playbook.plugins.<name>`
   usable with no change outside `content/`.
6. **History.** `git log --follow` on a moved file shows its pre-move history.

## Non-goals

- Changing the third-party overlay contract or the entry-point groups.
- Third-party packages under `coding_agent_playbook.plugins.*` or `.packs.*`.
  Both namespaces are reserved for bundled plugins.
- Supporting a namespace overlay whose single kind directory spans portions.
  This is pre-existing; only the comment is corrected.
- Publishing content as a separate distribution.
- Dropping `solution/` or `negatives/` from the wheel. Only tests read them,
  but changing what ships is out of scope.
- Tightening the link gate for overlays or repo-local layers.
- Fixing the pre-existing eval duplicate-id first-vs-last mismatch
  (`eval.py:218` vs `:461`).
- Rewriting historical `specs/*.md` or past SPEC changelog entries.
