# PR H — Agent Harness round-trip support (adapter + importer + validator)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.
>
> **Commit policy (overrides any tooling default):** every commit is authored **solely by `msobroza`** — **never** add a `Co-Authored-By:` trailer, never pass `--author`, never sign. Subagents and dispatchers must obey this too. **No `git push` / `gh pr create` until the user gate approves the diff.** Every dispatch prompt MUST start with `cd <worktree-path>` as its first tool call, and default to the `opus` model for every role.

**Goal:** Add bidirectional support for the [Agent Harness](https://agentharnesses.io/specification) format as a new, fully spec-conformant integration:

- **Track A — output adapter** (`agent_harness`): render canonical `Rule`/`Prompt`/`Skill` into a `HARNESS.md`-rooted harness tree. (Eval tasks are authoring-only and are not dispatched to adapters, so the adapter does not emit them — see §B.)
- **Track B — importer** (`playbook import-harness`): parse a harness tree back into canonical artifacts.
- **Track C — validator** (`playbook validate-harness`): run `harnesses-ref`-equivalent structural checks on a harness tree (emitted or foreign).

Round-trip fidelity is delivered by a `.playbook/` **dotfile sidecar manifest** (lossless when present; best-effort reconstruction otherwise). No edits to `renderer.py`, `orchestrator.py`, or `types.py` — every track is additive.

**Architecture:** One blocking core module (Track H1) then three additive tracks (H2/H3/H4) that depend on it, plus docs (H5). H1 is the substrate both directions share.

| Track | Files | Subagent worktree | LoC | Depends on |
| --- | --- | --- | --- | --- |
| H1 — harness core | `harness/__init__.py`, `harness/models.py`, `harness/leaf_detectors.py`, `harness/parser.py`, `harness/emitter.py`, `harness/manifest.py` + `tests/harness/{test_parser,test_emitter,test_leaf_detectors,test_manifest_roundtrip}.py` + fixtures | `prH-core` | ~600 | — |
| H2 — output adapter | `adapters/agent_harness_adapter.py`, `tests/adapters/test_agent_harness.py`, `pyproject.toml` entry point | `prH-adapter` | ~300 | H1 |
| H3 — importer | `commands/import_harness.py`, `cli.py` (subcommand), `tests/cli/test_import_harness.py`, `tests/harness/test_import_roundtrip.py` | `prH-importer` | ~300 | H1 |
| H4 — validator | `commands/validate_harness.py`, `cli.py` (subcommand), `tests/cli/test_validate_harness.py` | `prH-validator` | ~200 | H1 |
| H5 — docs/content | `SPEC.md` (§10/§12/§20), `README.md`, `CLAUDE.md` (refresh tracks table), example enablement | `prH-docs` | — | H1–H4 |
| Integration | merge + final CI gate (mypy + `pytest -q`, no path args) + PR | `prH-integration` | — | all |

> **cli.py conflict note:** H3 and H4 both append a line to `_SUBCOMMANDS` in `cli.py`. Sequence H4 after H3, or resolve the two-line add at integration. Keep the rest of each track in non-overlapping files.

**Tech Stack:** Python 3.12+, stdlib only (`pathlib`, `dataclasses`, `tomllib`/`tomli_w` already vendored by the lockfile track, `shutil`, `os`, `hashlib`, `stat`). No new runtime deps. `pyyaml` (already a dep) for frontmatter.

---

## Context for fresh subagents

You are working on `coding-agent-playbook` after PRs through #11 landed: the engine is complete (4 adapters, renderer, detector, filesystem sources, CLI, eval Tier 0). SPEC.md is canonical. This plan adds a **fifth output target** plus the reverse direction.

**Required reading before starting any track:**

1. The Agent Harness spec, all pages: https://agentharnesses.io/specification and the `harness-creation/*` + `client-implementation/*` pages. The **artifact catalog (§A below) is the distilled source of truth** — read it first.
2. `SPEC.md` §10 (adapter ABC + per-adapter responsibilities), §6 (canonical types), §4 (sync data flow), §20 (storage source abstraction).
3. `src/coding_agent_playbook/adapters/base.py` — the `Adapter` ABC you subclass for Track H2. Note `write_rule`/`write_prompt` (abstract), `write_skill`/`finalize`/`cleanup_stale`/`_output_directories`/`_default_cleanup` (overridable).
4. `src/coding_agent_playbook/adapters/claude_code_adapter.py` — the **reference** for native skill emission (`scripts/`+`references/` copytree), `finalize`-buffered composite files, and custom `cleanup_stale`.
5. `src/coding_agent_playbook/types.py` — `Rule`, `Prompt`, `Skill`, their frontmatter dataclasses, `to_dict`/`from_dict` round-trip contract (§6.6.3). Track B's round-trip test asserts equality through these.
6. `src/coding_agent_playbook/sources/filesystem.py` + `commands/sync.py` — how artifacts are loaded, rendered, and dispatched to adapters.

---

## §A — Definitive artifact catalog (the format, distilled)

This is the complete set the spec defines. There is **no** `AGENTS.md`, manifest, lockfile, `version`, `allowed-tools`, or `license` field anywhere in the spec.

| Artifact | Req? | Location | Schema | Notes |
| --- | --- | --- | --- | --- |
| `HARNESS.md` | **yes** | root, exactly one | frontmatter `name` (req), `description` (req) + markdown body | body injected every session; keep <300 tok ideal, <600 acceptable |
| Routing file `<DIR>.md` | optional* | each grouping dir in a branch | frontmatter `description` only (no `name`) + body | name = **top-level** ancestor `DIR.upper()+".md"`, **propagates through the whole subtree** |
| `SKILL.md` | leaf-req | a skill leaf dir | frontmatter `name`, `description` (**only 2 documented fields**) + body | body = the reasoning layer (when/why, how to invoke scripts) |
| `.leaf-detectors` | optional | **root only** | line-based `leaf_type=relative_path`; `#` comments; split on first `=` | e.g. `skill=SKILL.md`. Defines the leaf vocabulary + each leaf type's **primary file** |
| `.harnessleaf` | optional | **any** dir | **empty presence marker** (no contents) | dir becomes leaf type `"leaf"`; clients stop traversing and treat the dir as an opaque unit |
| `scripts/` | optional | inside a skill (sibling of `SKILL.md`) | dir of executable files; **no** root-level `scripts/` | run via `run_script(path, script, args)->str`; stdin/args in, stdout out, non-zero exit = failure, stderr = message. Enumerated (non-recursive `scripts/*`) and surfaced by `load_content` |
| md content file | optional | anywhere | optional `description` frontmatter + body | `description` drives Discovery relevance |
| raw/binary file | optional | anywhere | none | returned as raw bytes (`read_bytes().decode(errors="replace")`); never assume UTF-8 |
| top-level dirs | optional | root | none reserved | conventions seen: `skills/ references/ tools/ data/ outputs/ brand/ context/ environment/ campaigns/` — author-chosen |

\* `harnesses-ref validate` warns when a grouping subdir lacks a routing file, and when a content `.md` lacks `description`. The adapter emits both to stay warning-clean.

**Four loading phases (client runtime, modeled by Track C's validator, not implemented as a runtime):** Load (inject `HARNESS.md` body) → Discovery (read routing files) → Activation (`load_content`) → Execution (`run_script`).

---

## §B — Canonical → harness mapping & emitted tree (Track H2 contract)

```
<harness-root>/
├── HARNESS.md                 # name/description from config (repo-derived fallback);
│                              #   body = role summary + index of top-level dirs +
│                              #   "Always consult these" section pointing at rules/ (decision #2)
├── .leaf-detectors            # "skill=SKILL.md" when any skill/prompt leaf exists
│
├── skills/                    # ← canonical Skill
│   ├── SKILLS.md              #   routing file (description-only frontmatter)
│   └── <skill-id>/
│       ├── SKILL.md           #   name/description (1:1) + body
│       ├── scripts/           #   ← Skill.scripts_dir; bytes copied verbatim (copy2), exec flag in sidecar (decision #1)
│       │   └── <exec-file>    #   referenced in SKILL.md body as "**Script:** scripts/<f> <args>"
│       └── references/        #   ← Skill.references_dir (internal; protected by the leaf)
│
├── prompts/                   # ← canonical Prompt (own top-level dir disambiguates from skills)
│   ├── PROMPTS.md
│   └── <slash>/SKILL.md       #   skill-shaped leaf; includes_rules inlined via rule(); input_variables noted
│
├── rules/                     # ← Rule scope=always  (decision #2: rules/ + mandatory pointer from HARNESS.md)
│   ├── RULES.md
│   └── <priority:02d>-<id>.md #   md content file; description = Rule.description; body = rule body
│
├── references/                # ← Rule scope=scoped + raw assets (on-demand)
│   ├── REFERENCES.md
│   └── <id>.md | <raw-file>   #   md (description fm) | byte-for-byte passthrough
│
│                              # NOTE: no evals/ — eval tasks are authoring-only and are NOT
│                              # dispatched to adapters (the Adapter ABC has no eval hook; sync
│                              # only calls write_rule/write_prompt/write_skill/finalize). The
│                              # agent_harness adapter therefore never emits eval tasks, exactly
│                              # like the four existing adapters. The importer can still READ an
│                              # evals/ dir from a foreign harness; the adapter just never writes one.
│
└── .playbook/                 # SIDECAR (dotfile; clients skip dotfiles)
    ├── .harnessleaf           #   belt-and-suspenders terminal marker
    └── manifest.toml          #   lossless round-trip data — see §C
```

**Type → destination + fidelity split** (the sidecar stores the FULL canonical reconstruction payload — every field below *plus* the un-rendered source `body`, `name`, and `is_templated` for every kind; see §C):

| Canonical type | Harness destination | Native fields emitted on the leaf | Recorded in `.playbook/manifest.toml` (reconstruction payload) |
| --- | --- | --- | --- |
| `Skill` | `skills/<id>/SKILL.md` + `scripts/` + `references/` | `name`, `description`, body, script bytes | `name`, source `body`, extra open-dict frontmatter keys; per-script **`executable` flag** |
| `Prompt` | `prompts/<slash>/SKILL.md` | `name`, `description`, body (with `includes_rules` inlined) | `name`, **un-inlined source `body`**, `is_templated`, `slash`, `version`, `applies_if`, `input_variables`, `includes_rules`, `eval_tasks` |
| `Rule` (always) | `rules/<priority>-<id>.md` | `description`, body | `id`, **`name`**, source `body`, `is_templated`, `scope`, `globs`, `applies_if`, `priority`, `tags`, `version` |
| `Rule` (scoped) | `references/<id>.md` | `description`, body | same as above (esp. `name`/`globs`/`applies_if`) |
| `EvalTask` | **not emitted by the adapter** — authoring-only, never dispatched to adapters during sync (same as all four existing adapters). The importer reads a foreign `evals/` only. | — | — |

**Sentinel:** every generated text file carries the playbook `SENTINEL` as the **first body line** (an HTML comment) — frontmatter must stay on line 1 for the harness parser's `^---\n`, so the sentinel cannot be line 1. The adapter overrides `cleanup_stale` to detect `SENTINEL` **anywhere** in a file (not just line 1), mirroring the Claude Code/AGENTS.md single-file pattern. User-authored files (no sentinel) are never deleted. Scripts/raw assets are not text-stamped — their ownership is tracked via the sidecar manifest.

---

## §C — The `.playbook/manifest.toml` sidecar (round-trip contract)

Written by Track H2, read by Track H3. One entry per emitted artifact, keyed by its harness-relative path. The sidecar is the **full canonical reconstruction payload and the lossless source of truth** — not merely a stash of "non-native fields". For every artifact it records:

- **Every frontmatter field the harness format cannot represent** (e.g. a rule's `name`/`scope`/`globs`/`priority`/`tags`, a prompt's `slash`/`includes_rules`/`input_variables`/`eval_tasks`, a skill's `extra_frontmatter`). Notably the harness rule file emits only `description`, so the rule **`name`** is sidecar-only.
- **The original, un-rendered canonical source `body`** for *every* kind (rule, prompt, skill). The harness leaf is the client-facing *presentation* and may rewrite/inline content — a prompt's `includes_rules` are inlined into its `SKILL.md` body via `rule()`. The recorded `body` is the canonical text, so the importer never reconstructs from the rendered/inlined leaf.
- **`is_templated`** for every kind (tracks `.md` vs `.md.j2` origin) — including prompts (rules already did this).

Because the entry carries the whole payload, the lossless importer reconstructs each artifact via `from_dict` **independently of how the harness presentation rendered or inlined things** — the leaf files exist only for harness clients; the sidecar is authoritative.

```toml
schema = 1

[[artifact]]
kind = "rule"                       # rule | prompt | skill | eval_task
path = "rules/10-python-house-style.md"
id = "python-house-style"
name = "Python House Style (Human)"  # sidecar-only: the harness rule file emits description only
body = "# House style\n\nUse type hints.\n"   # un-rendered canonical source body
is_templated = false                # tracks .md vs .md.j2 origin
scope = "always"
priority = 10
globs = []
applies_if = {}
tags = ["python"]
version = 1

[[artifact]]
kind = "prompt"
path = "prompts/review/SKILL.md"
id = "review"
name = "Review"
body = "# Review\n\nReview the diff.\n"        # ORIGINAL body, NOT the includes_rules-inlined leaf
is_templated = true                            # a .md.j2 prompt round-trips as templated
slash = "review"
version = 3
includes_rules = ["python-house-style"]        # inlined into the leaf, recovered from here

[[artifact]]
kind = "skill"
path = "skills/query-database/SKILL.md"
id = "query-database"
name = "Query database"
body = "# Query database\n\nUse the run_query script.\n"
extra_frontmatter = { license = "MIT" }     # any open-dict key beyond name/description
[[artifact.script]]
path = "skills/query-database/scripts/run_query.py"
executable = true                          # git-style single bit, not full octal (decision #1)
[[artifact.script]]
path = "skills/query-database/scripts/_db.py"
executable = false                         # imported helper — stays non-exec
```

**Fidelity tiers (Track H3):**
- **Lossless** — `.playbook/manifest.toml` present: rebuild each canonical artifact from the path→entry index using the entry's full payload (full frontmatter incl. rule `name`, the un-rendered source `body`, and `is_templated`); `description` is read back from the natively-emitted leaf frontmatter. Restore each script's `executable` bit on POSIX (`os.chmod(p, mode | 0o111)` when true, no-op on Windows). Reconstruction does **not** depend on the rendered/inlined leaf body. Must satisfy the `to_dict` round-trip contract (SPEC §6.6.3) **plus** a file-level assertion for scripts — see §C note.
- **Best-effort** — no sidecar (foreign harness): infer from structure (skill leaf → `Skill`; `prompts/*` → `Prompt`; `rules/*.md` → `Rule` scope=always; `references/*.md` → `Rule` scope=scoped; raw files → opaque asset). Non-native fields defaulted, `name` defaults to the id, and the body is taken from the (possibly inlined) on-disk leaf; **surface the lossiness, do not silently guess** (CLAUDE.md). Without a sidecar, a script's `executable` intent is inferred from the on-disk bit (whatever survived transport) and cannot be guaranteed.

**Importer write-back location:** the importer writes **all** reconstructed rules — `scope=always` *and* `scope=scoped` — to `<into>/rules/<id>.md`. That is the only directory `FileSystemArtifactSource.list_rules()` reads, so a scoped rule written to `references/` would be silently dropped on the next `playbook sync`. `scope` is preserved in the rule's frontmatter (emitted by `to_markdown`), so a scoped rule stays scoped without needing a separate directory.

> **§C note — scripts are not covered by `to_dict`.** `Skill.to_dict()` serializes frontmatter + body + `scripts_dir` as a *path*, not per-file bytes or modes. The lossless round-trip therefore needs a **separate file-level assertion**: every script under `scripts/` must match byte-for-byte **and** its `executable` flag must match (POSIX). Track B's round-trip test asserts both, not just artifact equality.

---

## §D — Four locked design decisions

1. **Script executability** → *copy bytes (`shutil.copy2`) + record a per-script boolean `executable` flag in the sidecar.* Use git's single-bit model, **not** a full octal mode (which would bake in umask-dependent group/other bits and risk widening permissions). `copy2` makes committed-harness + git transport already correct; the sidecar flag makes it **guaranteed and testable** for zip/foreign/non-git transport. Importer restores the exec bit on POSIX (`mode | 0o111`), no-ops on Windows. Per-file faithful: entrypoints stay executable, libraries/data files inside `scripts/` stay non-exec.
2. **`scope=always` rules** → *`rules/` + mandatory pointer.* Emit as `rules/<id>.md`; `HARNESS.md` body adds an "Always consult these" section instructing the agent to read them every session. Keeps the body small and spec-idiomatic.
3. **Client runtime** → *add a `validate-harness` lint command (Track C).* The playbook does **not** implement `load_content`/`run_script` as a runtime; it validates structure (`harnesses-ref`-equivalent). Full client modeling is future work (note in SPEC).
4. **Next step** → this spec doc; implementation gated behind user approval.

---

## Track H1 — harness core module (BLOCKER)

**Files:** `src/coding_agent_playbook/harness/{__init__,models,leaf_detectors,parser,emitter,manifest}.py` + `tests/harness/`.

- [ ] `models.py` — dataclasses: `Harness(name, description, body, path, directories)`, `HarnessDirectory(name, routing_file_name, description, path, children, leaves, content)`, `SkillLeaf(name, description, body, path, scripts, references)`, `ScriptFile(path, executable: bool)`, `ContentFile(filename, description, path, is_markdown)`, `RawAsset(path, sha256)`, `LeafMarker`. Frozen where practical.
- [ ] `leaf_detectors.py` — `parse_leaf_detectors(text) -> dict[str,str]` (skip blank/`#`, split first `=`, strip both sides); `routing_file_name(top_level_segment) -> str` (`segment.upper()+".md"`); `is_harness_leaf(dir) -> bool`; `leaf_type(dir, detectors) -> str | None`.
- [ ] `parser.py` — `parse_harness(root: Path) -> Harness`. Require `HARNESS.md` (else raise `NotAHarnessError`). Load root `.leaf-detectors`. Walk **every** top-level dir (no name filter); derive routing name from the top-level segment and propagate; classify each dir via `.harnessleaf` (→ `"leaf"`, opaque) then detectors (→ typed leaf, stop) else grouping (recurse). Skill leaves parse `SKILL.md` frontmatter + capture `scripts/*` (filenames + `executable` flag from the on-disk bit) + internal `references/`. Markdown files → `ContentFile` (optional `description`); others → `RawAsset` (sha256, bytes). Never assume UTF-8 for raw files.
- [ ] `emitter.py` — pure helpers used by the adapter: `routing_file(description, body) -> str`; `frontmatter_block(fields) -> str`; `with_sentinel_body(frontmatter, body) -> str` (sentinel as first body line); `copy_script(src, dst) -> bool` (uses `shutil.copy2`, returns whether the source bit was executable); `leaf_detectors_file(types) -> str`; `harnessleaf_path(dir)`.
- [ ] `manifest.py` — `ManifestEntry`/`Manifest` dataclasses; `write_manifest(root, entries)`; `read_manifest(root) -> Manifest | None`; path→entry index helper.
- [ ] Tests: `test_leaf_detectors.py` (parse edge cases, comments, no-trailing-newline, propagation rule), `test_parser.py` (parse the upstream `examples/` fixtures + a `.harnessleaf` dir + a skill-with-scripts; assert leaf typing and over-traversal protection), `test_emitter.py` (sentinel placement; `copy_script` preserves bytes and reports the exec bit), `test_manifest_roundtrip.py`.
- [ ] Fixtures under `tests/harness/fixtures/`: a copy of an upstream example harness, a skill-with-scripts (exec bit set), a `.harnessleaf`-terminated dir.
- [ ] Local gate: `uv run mypy` and `uv run pytest -q` from repo root (no path args), 80%+ coverage on new files.

---

## Track H2 — output adapter

**Files:** `src/coding_agent_playbook/adapters/agent_harness_adapter.py`, `tests/adapters/test_agent_harness.py`, `pyproject.toml`.

- [ ] `class AgentHarnessAdapter(Adapter)` with `name = "agent_harness"`. Accept `rule_registry: RuleRegistry | None = None` in `__init__` (for `includes_rules` inlining), mirroring `continue_adapter.py`.
- [ ] **Buffer** rules/prompts/skills in `write_rule`/`write_prompt`/`write_skill` (these are the ONLY hooks the ABC/sync provide — there is no eval-task hook); compose the whole tree in `finalize` (so `HARNESS.md` body can reference everything). Skills emit native `SKILL.md` + `scripts/` (via `emitter.copy_script`, capturing each `executable` flag for the manifest) + `references/`.
- [ ] Emit `.leaf-detectors` (`skill=SKILL.md`) when any skill/prompt leaf exists; emit `.harnessleaf` for `.playbook/`.
- [ ] Write `.playbook/manifest.toml` via `manifest.write_manifest` with every non-native field + each script's `executable` flag.
- [ ] Override `cleanup_stale` to delete files containing `SENTINEL` anywhere within the harness output dirs that aren't in `written_paths`; never touch non-sentinel (user) files; track scripts/raw via the previous manifest.
- [ ] `pyproject.toml`: add `agent_harness = "coding_agent_playbook.adapters.agent_harness_adapter:AgentHarnessAdapter"` under `[project.entry-points."coding_agent_playbook.adapters"]`. **Opt-in** — not added to `_DEFAULT_ADAPTERS`.
- [ ] Tests: golden tree shape; sentinel-in-body; `.leaf-detectors` content; `.harnessleaf` on `.playbook/`; no `evals/` emitted; script bytes + recorded `executable` flag (incl. a non-exec file in `scripts/` staying non-exec); manifest completeness; `cleanup_stale` removes stale sentinel files but preserves user-authored ones.

---

## Track H3 — importer

**Files:** `src/coding_agent_playbook/commands/import_harness.py`, `cli.py`, `tests/cli/test_import_harness.py`, `tests/harness/test_import_roundtrip.py`.

- [ ] `playbook import-harness <harness-path> [--into <dir>]` (default `--into playbook/`). `run(args) -> int` (module pattern, like other commands).
- [ ] Use `harness.parser.parse_harness` + `harness.manifest.read_manifest`. Lossless when manifest present; best-effort otherwise (§C). Best-effort lossiness is reported to stderr, not silently applied.
- [ ] Map back to canonical types and write them as `.md`/`.md.j2` + `task.toml` under the target overlay dir, restoring each script's exec bit on POSIX (per the sidecar `executable` flag; no-op on Windows).
- [ ] Register `import-harness` in `_SUBCOMMANDS` (`cli.py`).
- [ ] Tests: `test_import_roundtrip.py` — canonical → H2 adapter → H3 importer → canonical, assert artifact equality via `to_dict` **and** a file-level check on every script (bytes + `executable` flag, since `to_dict` doesn't cover modes — see §C note). `test_import_harness.py` — best-effort import of an upstream `examples/` harness; CLI exit codes; lossiness reporting.

---

## Track H4 — validator

**Files:** `src/coding_agent_playbook/commands/validate_harness.py`, `cli.py`, `tests/cli/test_validate_harness.py`.

- [ ] `playbook validate-harness <path>` — structural checks equivalent to `harnesses-ref validate`: `HARNESS.md` present + `name`/`description` non-empty; every detected skill leaf has `name`+`description`; **warn** when a grouping subdir lacks its routing file; **warn** when a content `.md` lacks `description`. Non-zero exit on errors; warnings don't fail by default (`--strict` promotes warnings to errors).
- [ ] Reuse `harness.parser` (don't re-walk). Register `validate-harness` in `_SUBCOMMANDS` (sequence after H3 or resolve the two-line `cli.py` add at integration).
- [ ] Tests: valid harness passes; missing `name` fails; missing routing file warns; `--strict` flips warnings to non-zero.

---

## Track H5 — docs & content

- [ ] `SPEC.md`: new §10.x documenting the `agent_harness` adapter + sidecar; §12 entries for `import-harness` and `validate-harness`; §20 note on the sidecar `StateSource`-adjacent manifest; a future-work note for the client runtime contract (decision #3).
- [ ] `README.md`: document the 5th adapter, the importer, and the validator.
- [ ] `CLAUDE.md`: refresh the stale "status: not started" tracks table; add `agent_harness` invariants (sentinel-in-body, `.harnessleaf` for non-routed dirs, copies-not-symlinks for scripts with the `executable` flag in the sidecar).
- [ ] Optionally enable `agent_harness` in an example/integration test repo.

---

## Invariants this PR must honor (CLAUDE.md + SPEC §4.3)

- **Copies, not symlinks** — scripts/raw assets are byte-copied (`shutil.copy2`); each script's `executable` flag (git's single bit, not full octal) is recorded in the sidecar.
- **Sentinel present** — every generated text file carries `SENTINEL` (first body line); `cleanup_stale` overridden to detect it anywhere.
- **`StrictUndefined`** — never disabled.
- **Frontmatter is static YAML, parsed before Jinja** — never templated; harness frontmatter stays on line 1.
- **Rules cannot include other rules** — `rule()` helper only in prompt context; harness prompt-leaf inlining uses the existing registry.
- **AGENTS.md is always generated** — unaffected; `agent_harness` is one more adapter alongside it.
- **Never instantiate adapters directly** — `agent_harness` is discovered via entry point; `name` == entry-point key.

---

## Open fidelity risks (tracked, not blocking)

1. `SKILL.md` frontmatter is underspecified (only `name`/`description`); extra Skill keys round-trip via the sidecar only.
2. `includes_rules` is inlined into the prompt leaf for harness clients (one-way *presentation*), but the **sidecar recovers the original un-inlined prompt body** plus the `includes_rules` list, so a lossless import reconstructs the un-rendered prompt exactly. Only a sidecar-less (foreign) harness loses the un-inlined body — best-effort then takes the inlined leaf body and drops `includes_rules`.
3. Rule scoping (`scope`/`globs`/`applies_if`) and the rule **`name`** have no harness home → recorded in the sidecar (the rule leaf emits `description` only), so they round-trip losslessly. Best-effort import (no sidecar) falls back to directory-placement heuristics (`rules/` → always, `references/` → scoped) and defaults `name` to the id.
4. EvalTasks are non-native AND not dispatched to adapters during sync (no eval hook on the ABC), so the adapter does not emit them at all — consistent with every existing adapter. Eval-task round-trip is therefore out of scope for the adapter; only the importer would handle a foreign `evals/` dir if present.
5. Executable-bit preservation is lossy on Windows working trees (no POSIX bit) — mitigated by the sidecar `executable` flag + POSIX-only restore, and by git's tree object carrying the bit for committed harnesses. `to_dict` does not cover script modes, so round-trip fidelity for scripts is verified by a separate file-level assertion (§C note), not artifact equality alone.
6. Raw/binary assets have no canonical home → passthrough asset class tracked by checksum in the sidecar.
