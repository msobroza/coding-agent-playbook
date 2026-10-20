# PR F: forge adapter (`gh` or `glab`, chosen from git config)

Status: design approved in a grilling session on 2026-10-19 to 2026-10-21 (decisions Q1 to Q64, listed in §2). Not implemented.
ADR: [docs/adr/0003-forge-clis-are-reached-only-through-playbook-forge.md](../docs/adr/0003-forge-clis-are-reached-only-through-playbook-forge.md).
Glossary: **Forge**, **Forge CLI**, **Forge operation**, **Pull request** (CONTEXT.md, *Forges*).

## 1. Goal

A consumer repo hosted on GitHub or GitLab gets the same experience and the same guardrails:

1. **One command, either forge.** `playbook forge <operation>` reads the repo's git config on every call, decides whether the forge is GitHub or GitLab, and runs `gh` or `glab` with translated arguments. Skills and agents name only `playbook forge`.
2. **Transparent for plugin users.** With the bundled `mattpocock_skills` plugin on, a user whose repo pushes to GitHub or GitLab confirms "Forge issues" once in setup and never sees `gh`, `glab` or `playbook forge` again.
3. **GitLab parity in every guard.** Every control written for `gh` and GitHub today (exfil, taint, push policy, secrets, CI twins, gate-scan) recognises `glab`, GitLab tokens, GitLab CI and `playbook forge`, offline.

Non-goals: rendering forge-specific text at sync time (rejected, ADR 0003); a plugin entry point for third-party forges (Q3: a fixed in-tree list, one entry per forge); hooks that contact a forge; CI secret or variable writes; issue deletion; attachment upload; guarding forge merges and destructive forge commands (deferred, on neither forge today).

## 2. Decision record

| Q | Decision |
|---|---|
| Q1′ | Scope is **A** (guards recognise both forges) + **B** (the engine runs `gh`/`glab`). **C** (render per-forge text) is dropped. |
| Q2 | Glossary term **Forge**; the code is never called an "adapter" (that word means a harness adapter). |
| Q3 | Forges are a fixed in-tree list (`GITHUB`, `GITLAB`); a third forge is one more entry. |
| Q5 | Canonical term **pull request**; "merge request" / "MR" only when quoting GitLab. |
| Q7 | Guards recognise every forge CLI in every repo, whatever the repo's own forge. |
| Q9 | Only `playbook forge` contacts a forge, and only when someone runs it. Never hooks, `sync`, `check`, `validate` or `playbook ci`. |
| Q10 | `playbook forge` runs the CLIs as subprocesses with their own login. The engine never reads or stores a token. |
| Q12 | A covers GitLab parity, the egress gaps both forges share, and the GitLab CI fixes. |
| Q13 | Forge commands that push (`glab mr create --fill/--push`, `repo create --push`) count as `git push` for every push-scoped guard. |
| Q14 | GitLab token rules, `glab` credential files, the GitLab Runner config; prefixes re-verified at implementation time. |
| Q15 | A runtime command, `playbook forge <operation>` (adapter pattern), with per-forge tables shared with the guards. |
| Q16 → Q27 | Operations: every forge operation the mattpocock skills use (vendored v1.3.1 and installed 1.2.3), plus `pr checks`, `ref view`, `which`, `auth status`. |
| Q17 | The forge comes from the current branch's push remote: `branch.<b>.pushRemote` → `remote.pushDefault` → `branch.<b>.remote` → `origin`. |
| Q18 | Host → forge: `[forge]` table → exact `github.com`/`gitlab.com` → host name containing `github`/`gitlab` → host equal to a forge host env var → exit 2. Never contacts the network, never reads CLI credential files. |
| Q19 | A new stdlib-leaf package `forge/` (§4). |
| Q20 | Read operations print the same JSON shape on both forges. |
| Q21 | Escape hatch: `playbook forge which`; no raw passthrough. |
| Q22 | `pr comment --reply-to <id>` replies inside a review thread. |
| Q23 → Q47 | An **always-present** core skill `forge` (skills cannot carry `applies_if`; no detector fact). |
| Q24 | Tests use fake `gh`/`glab` executables on `PATH`; a manual check before release. |
| Q26 → Q45 | Forge tickets F1 to F7 under a new forge tracker, squashed onto `integration/skills-and-layout` with the layout protocol. |
| Q28 | The vendored plugin gains a "Forge issues" tracker option that names only `playbook forge`. |
| Q29 | No `secret set` / `variable set`; `auth status` only. Wizard keeps guiding the human. |
| Q30 | An operation a forge or plan lacks exits 3; the skill applies its text fallback. |
| Q31 | `playbook forge ref view <ref>` resolves `#n`, `!n` and URLs. |
| Q32 | Setup detects the forge and preselects "Forge issues"; the user confirms once (D14's default changes from "always local markdown"). |
| Q33 | The plugin stays opt-in (`overlays_enabled`, D3). |
| Q34 | A missing or logged-out CLI makes setup and every operation show the one human step; no fallback to local markdown or raw API calls. |
| Q35 | Hooks guard `playbook forge` and are built on the same `forge/` tables; hooks never call a forge. |
| Q36 | Bodies: `--body TEXT`, `--body-file PATH`, `--body-file -` (stdin), translated for `glab`. |
| Q37 | Exit codes 0 / 1 / 2 / 3 (§6.2). |
| Q38 | Minimum `gh` 2.94.0 and `glab` 1.115.0, checked per call; no REST fallbacks. |
| Q39 | Composite tracker logic (wayfinder's frontier) stays in skills, over primitive operations. |
| Q40 | Line-leading `/` is neutralised in every body sent to GitLab (quick actions). |
| Q41 | `issue close --comment --reason`: one call on GitHub, note then close on GitLab. |
| Q42 | Missing labels: accept the forge difference; setup creates labels on both forges. |
| Q43 | `playbook forge pr create` never pushes. |
| Q44 | `issue delete` and attachment upload are out; wayfinder closes obsolete tickets as not-planned. |
| Q46 | Ticket order (§12). |
| Q48 | Guards never read `[forge]`; `[forge]` is not policy and is not control-plane protected. |
| Q49 | F6 amends D2/D13/D14 with every pinned test, and adds GitLab CI/CD variable guidance to wizard. |
| Q50 | Forge-neutral hardening found on the way is a separate ticket F7. |
| Q51 | A push-option judge (§8.4). |
| Q52 | README documents how to make `playbook ci` a real gate on GitLab; gate-scan flags weakening of the `playbook-ci` job. |
| Q53 | The GitLab CI recipe passes `--base` explicitly and fetches the target branch; `playbook ci` fails closed on an empty range; draft prefixes are stripped from the title. |
| Q54 | gate-scan's GitLab grammar is pattern-based (§10.3). |
| Q55 | `playbook forge` refuses `[skip ci]` titles, exposes `confidential`, disables CLI telemetry, exits 2 on a host mismatch. |
| Q56 | `--template` paths are body files; extra glab host variables; snapshot URLs without credentials; `glab -t/-j` redaction; custom PAT prefix via `extra_patterns`. |
| Q57 | Text-only fixes folded into F4/F6. |
| Q58 | This spec, ADR 0003 and the glossary terms land as one docs PR to `main`. |
| Q59 | Machine B: F1, F2, F3, hook parts of F7. Machine A: F4, F5, F6. |
| Q60 | `playbook forge` passes the remote's host to the CLI (`GITLAB_HOST` / `GH_HOST`) on every call. |
| Q61 | A `[forge]` host entry may carry `api_host`; SSH aliases resolve offline with `ssh -G`. |
| Q62 | `playbook forge -C <path>`; outside a git repo, exit 2 with a hint. |
| Q63 | A README section *Running on Domino Data Lab* plus Domino-aware exit-2 hints. |
| Q64 | F7 blocks commands that print forge tokens; one GitLab token per environment is a documented limit. |

## 3. Background: what exists today

Audited on `main` (13177c9) and `integration/skills-and-layout` (e398bb3) with simulate runs. Today the engine never runs `gh`; it only reads commands the agent runs. GitLab works only where the code was never forge-specific: the git push and remote guards, host extraction for any git URL, curl uploads to `/api/v4`, unattended detection (`CI=true`), `.gitlab-ci.yml` in `has_ci`, MCP tool classification. Every control written for GitHub has no GitLab counterpart:

- `glab` is in no guard's prefilter: `glab snippet create notes.md` returns none where `gh gist create notes.md` asks.
- No secret rule matches a GitLab token; `~/.config/glab-cli/config.yml` is not a secret path.
- `glab mr create --fill` pushes past every push-scoped guard; `push_requires_green` knows only `gh pr create`.
- gate-scan watches only `.github/workflows/*` step removals.
- `playbook ci` in a GitLab merge request pipeline exits 2 (the target branch is never fetched) with an `actions/checkout` hint.
- No test exercises a GitLab path.

A GitHub-side bug found on the way (the `github-token` rule never matches `github_pat_`) is fixed separately.

## 4. Package layout

Paths are the final layout of `specs/prT-package-layout.md`, read on `integration/skills-and-layout`.

```
src/coding_agent_playbook/forge/        F1, stdlib-only leaf
├── __init__.py      docstring only (ADR 0002, L5)
├── dialects.py      per-forge tables: argv0, subcommands, value-taking flags, file-carrying
│                    flags, pushing subcommands and flags, host env vars, token env vars
├── hosts.py         pure functions: remote URL → host → forge, given the [forge] table and
│                    the environment as arguments
└── operations.py    the forge-operation catalogue: name, arguments, kind (read / write /
                     sends data / pushes), per-forge translation rules
```

- Import-linter: the bottom layer becomes `"security | toml_writer | forge | (_plugin_registry)"`. `coding_agent_playbook.forge` joins the `stdlib-leaves` `source_modules` (sorted, after `detector.pyproject_deps`) and `tests/engine_modules.py` `STDLIB_LEAVES` and `_TARGET_PACKAGES`. The forbidden lists are derived and do not change; no ignore lines. F1's PR body cites F3's hot-path need (R5).
- `forge/` imports only the standard library and other leaves: no `hook_runtime`, `config`, `security`. It never imports `subprocess`, `socket`, `yaml`, `tomllib`, `jinja2`, `packaging`, `importlib.metadata` or `argparse` (hot-path budget). Tables are plain data (tuples and frozensets of flag names); `hook_runtime` turns them into its own `value_options()` / `CliWords`.
- Elsewhere:

| Piece | Location | Ticket |
|---|---|---|
| The command: subprocess, JSON normalisation, exit codes | `commands/forge.py` + private `commands/_forge_*.py` (B9's `Command` shape: `NAME`, `HELP`, `configure`, `run`) | F4 |
| `[forge]` parsing | `config/tables/forge.py` via `_table_shapes.read_table`; errors through validation | F4 |
| Guards | `hook_runtime/handlers/safety/{_egress,exfil_channel_guard,taint_escalation,_net_targets,network_egress_guard,git_commit_push_policy_guard,secret_content_guard,commit_message_convention}.py`, `handlers/verify/{block_precommit_bypass,_bypass_rules}.py`, `handlers/audit/_activity_record.py`, `hook_runtime/judges/{hosts,cli_words}.py`, `hook_runtime/shell/wrapper_policy.py` | F3 |
| Token rules, credential globs | `security/patterns.py` only | F2 |
| CI twins | `commands/twins/{_git_scope,_ci_commit_convention,ci}.py`, `hook_runtime/judges/_gate_weakening_files.py` | F5 |
| Core skill | `catalog/core/skills/forge/` | F4 |
| Tests | `tests/forge/`, `tests/cli/test_forge.py`, `tests/config/test_tables_forge.py`, `tests/hook_runtime/handlers/safety/…`, `tests/hook_runtime/judges/…`, `tests/security/…` | each |

## 5. Forge detection

### 5.1 Which remote

`playbook forge` runs in the working directory, or in `-C <path>`. It reads git config without contacting the network:

1. If `git symbolic-ref -q HEAD` names a branch `<b>`: `branch.<b>.pushRemote`, then `remote.pushDefault`, then `branch.<b>.remote`, then `origin`.
2. On a detached `HEAD` (CI, Domino commit launches): `remote.pushDefault`, then `origin`. Operations that need a branch (`pr create`) exit 2: "detached HEAD: run `git checkout -b <name>`".
3. Outside a work tree: exit 2, "run from the repo" (on Domino: "`/mnt/code` or `/repos/<name>`").

The URL is `remote.<r>.pushurl`, else `remote.<r>.url`, read raw; `git remote get-url --push` (after `insteadOf`) is tried only if the raw host does not map. Parsing accepts scp-like (`git@host:path`), `ssh://user@host:port/path` and `https://user:token@host:port/path`. Errors and logs print the host only, never the URL.

### 5.2 Host to forge

First match wins:

1. `[forge] hosts` in the committed `.coding-agent-playbook.toml` (§5.4).
2. Exact `github.com` → GitHub, `gitlab.com` → GitLab.
3. A host name containing `github` or `gitlab`.
4. A host equal to `GH_HOST` (GitHub) or `GITLAB_HOST` / `GITLAB_URI` / `GL_HOST` (GitLab), compared as lower-cased host names (scheme, userinfo, port, path stripped).
5. Otherwise exit 2: "unknown forge for host `<host>`; add it to `[forge] hosts`".

An SSH host is first resolved offline with `ssh -G <host>` (aliases, `altssh.gitlab.com`).

### 5.3 What the CLI is told

Every call sets, in the child environment only: `GITLAB_HOST=https://<api host>` or `GH_HOST=<api host>` (Q60), where the API host is the `[forge]` `api_host` or the remote host; `GH_PROMPT_DISABLED=1`, `GLAB_NO_PROMPT=true`, `GH_NO_UPDATE_NOTIFIER=1`, `GH_NO_EXTENSION_UPDATE_NOTIFIER=1`, `GH_TELEMETRY=false`, `DO_NOT_TRACK=1`, `GLAB_CHECK_UPDATE=false`, `GLAB_SEND_TELEMETRY=false` (Q55). If `GITLAB_API_HOST` (or a `glab` `api_host` reported by `glab config get api_host --host <host>`) names a different host than the API host, exit 2 (Q55).

### 5.4 `[forge]`

```toml
[forge]
# Only for hosts the rules in §5.2 cannot name.
hosts = { "git.acme.com" = "gitlab", "ssh.acme.com" = { forge = "gitlab", api_host = "gitlab.acme.com" } }
```

Values are `"github"` or `"gitlab"`, or a table with `forge` and optional `api_host`. Read only by `playbook forge`; guards never read it (Q48). Not in `Config`, `CONFIG_MANAGED_KEYS` or `schema._TABLE_HINTS`; the file name comes from `CONFIG_FILENAME`. `playbook validate` reports unknown keys and values.

## 6. `playbook forge`

### 6.1 Command line

```
playbook forge [-C <path>] <noun> <verb> [arguments] [--json]
```

Bodies (Q36): `--body TEXT`, `--body-file PATH`, `--body-file -` (stdin). For `glab` the adapter passes `--description-file -` / `mr note create` on stdin, so a body never goes on argv. Every body sent to GitLab has each line-leading `/` neutralised (Q40); only dedicated operations (`issue block`) send quick actions.

### 6.2 Exit codes

| Code | Meaning | The agent should |
|---|---|---|
| 0 | success | continue |
| 1 | the CLI failed; its stderr passes through unchanged | read the error |
| 2 | a human must fix something: unknown forge, CLI missing or below the minimum version, not logged in, detached HEAD, outside a repo, host mismatch, branch not pushed | stop and pass the one-line hint to the user |
| 3 | unsupported on this forge or plan | apply the skill's text fallback |

Hints name the human step: install `glab` ≥ 1.115, `glab auth login` or `GITLAB_TOKEN` / `GITLAB_ACCESS_TOKEN` / `OAUTH_TOKEN`, `gh auth login` or `GH_TOKEN`. With `DOMINO_PROJECT_ID` set (Q63): "add `GITLAB_TOKEN` under Account Settings → User environment variables and start a new workspace"; "add `glab` to the compute environment's Dockerfile".

### 6.3 Operations

`gh` ≥ 2.94.0 and `glab` ≥ 1.115.0 (Q38), checked with `--version` once per call. JSON on stdout for read operations; write operations print the new URL.

| Operation | GitHub | GitLab | Kind |
|---|---|---|---|
| `issue create --title --body… [--label]… [--assignee @me] [--parent n] [--blocked-by n,…] [--confidential]` | `gh issue create … --body-file -` | `glab issue create … --description-file - --yes`; `--parent` exits 3 (skill writes `Part of #n`); `--blocked-by` via a link (Premium, else exit 3) | sends data |
| `issue view <n> [--comments]` | `gh issue view --json …` | `glab issue view -F json --comments`, notes paginated, system notes dropped | read |
| `issue list [--state] [--label]… [--no-label] [--assignee] [--search] [--limit]` | `gh issue list --json …` | `glab issue list -O json …` | read |
| `issue comment <n> --body…` | `gh issue comment --body-file -` | `glab issue note` on stdin | sends data |
| `issue label <n> [--add a,b] [--remove c]` | `gh issue edit --add-label/--remove-label` | `glab issue update --label/--unlabel` (one request) | write |
| `issue close <n> [--comment] [--reason completed\|not-planned\|duplicate]` | `gh issue close …` | note (reason as a closing line), then `glab issue close`; a failed second call exits 1 naming the posted note | sends data |
| `issue assign <n> --add @me` | `gh issue edit --add-assignee @me` | `glab issue update --assignee +@me` | write |
| `issue edit <n> [--title] [--body…]` | `gh issue edit --body-file -` | `glab issue update --description-file -` | sends data |
| `issue link-child <parent> <child>` | `gh issue edit <parent> --add-sub-issue <child>` | exit 3 | write |
| `issue children <parent>` | `gh issue view --json subIssues` | exit 3 | read |
| `issue block <child> <blocker>` | `gh issue edit --add-blocked-by` | `/blocked_by` note (Premium), else exit 3 | write |
| `issue blockers <n>` | `gh issue view --json blockedBy` | `glab api projects/:id/issues/<iid>/links` (`is_blocked_by`), exit 3 on Free | read |
| `label list` / `label create <name> [--color] [--description]` | `gh label list --json` / `gh label create` | `glab label list -F json` / `glab label create --name` | read / write |
| `pr create --title --body… [--base] [--draft]` | `gh pr create --head <branch> …` | `glab mr create --source-branch … --description-file - --push=false --yes` | sends data |
| `pr view <n> [--comments]` | `gh pr view --json …` | `glab mr view -F json --comments` | read |
| `pr list [--state] [--label] [--external]` | `gh pr list --json`; `--external` via `gh api …/pulls` `author_association` | `glab mr list -F json`; `--external` via one membership lookup per author | read |
| `pr diff <n>` / `pr checkout <n>` | `gh pr diff --color never` / `gh pr checkout` | `glab mr diff --color never` / `glab mr checkout` | read |
| `pr comment <n> --body… [--reply-to <id>]` | `gh pr comment`; reply via `gh api …/pulls/<n>/comments/<id>/replies` | `glab mr note create` on stdin; reply via `glab api …/discussions/<id>/notes` | sends data |
| `pr label` / `pr close` / `pr ready` / `pr edit` | `gh pr edit`, `gh pr close`, `gh pr ready`, `gh pr edit --body-file -` | `glab mr update --label/--unlabel`, note then `glab mr close`, `glab mr update --ready`, `glab mr update --description-file -` | write / sends data |
| `pr checks <n>` | `gh pr checks --json` | `glab ci status` on the MR's pipeline | read |
| `ref view <ref>` | `#n`/`n`: PR, falling back to issue | `#n` issue, `!n` MR; URLs by path | read |
| `which` | prints `{forge, cli, host, api_host, repo, remote}` | same | read |
| `auth status` | `gh auth status --hostname <host>` | `glab auth status --hostname <host>` (never `-t`) | read |

Rules:

- `pr create` never pushes (Q43). If the branch is not on the remote, exit 2: "push the branch first (`git push -u <remote> <branch>`)". A title matching `(?i)\[(skip ci|ci skip|skip pipeline|no ci)\]` is refused on GitLab with exit 1 (Q55); `pr edit --title` likewise.
- JSON shapes (Q20) use one vocabulary: `number`, `url`, `title`, `body`, `state` (`open`/`closed`/`merged`), `labels` (names), `assignees` (logins), `author` (login), `created_at`, `updated_at`, `comments[]` (`id`, `author`, `body`, `created_at`), `confidential` (always `false` on GitHub), and for PRs `draft`, `base`, `head`. GitHub-only `author_association` appears only on `pr list --external` results.
- Out (Q29, Q44): `issue delete`, attachment upload, `secret set`, `variable set`, merges.

### 6.4 The core `forge` skill

`catalog/core/skills/forge/SKILL.md`, always rendered (Q47; `_ENGINE_SKILL_COUNT` 5 → 6). Its description says it applies when the repo is on GitHub or GitLab. It names the operations, the exit codes and what the agent does on 2 and 3, the PR and MR template locations (`.github/pull_request_template.md`, `.gitlab/merge_request_templates/`), and "ask before copying a confidential issue into a pull request". No always rule names `forge`; description budgets as for every core skill.

## 7. GitLab secrets (F2)

In `security/patterns.py` (zero runtime imports; bump `SECRET_RULESET_VERSION`; regenerate `destructive.json`):

- A `gitlab-token` rule in the module's literal-prefix-then-look-behind style covering `glpat-`, `gloas-`, `gldt-`, `glrt-`/`glrtr-`, `glptt-`, `glft-`, `glcbt-` (legacy `glcbt-<1-5>_<20>` and the JWT form), `glsoat-`, `glimt-`, `glagent-`, `glffct-`, `glwt-`; a `gitlab-runner-registration-token` rule for `GR1348941…`. Re-verify prefixes and lengths against GitLab's token overview when implementing.
- Credential globs beside `~/.config/gh/hosts.yml`: `~/.config/glab-cli/config.yml`, `~/Library/Application Support/glab-cli/config.yml`, `~/AppData/Local/glab-cli/config.yml`, the repo-anchored `.git/glab-cli/config.yml`, and the GitLab Runner `config.toml` locations. `~/.config/glab-cli/aliases.yml` stays not secret.
- Docs: `GLAB_CONFIG_DIR` and an admin-changed PAT prefix (Q56) are handled by documented `[guardrails.secrets] extra_globs` / `secret_rules.extra_patterns` rows.
- Consumers that gain the rules: secret-content-guard, the Stop sweep, `playbook scan-secrets`, the `playbook ci` scan row, compaction masking, activity-record redaction.

## 8. Guards (F3)

Built on `forge/dialects.py` and `forge/operations.py`. Offline; no subprocess on the Bash hot path; no `[forge]` read.

### 8.1 Recognition

- `glab` joins the prefilter `argv0s` of exfil, git_policy, secret_content (push scan), commit_convention and precommit_bypass, and `shell/wrapper_policy._GUARDED` (`playbook` is already there).
- `playbook forge <operation>` is recognised from `forge/operations.py`: operations of kind *sends data* with `--body-file PATH` are body-file egress; `pr create` triggers `push_requires_green`.
- Activity record: `glab` joins `SUBCOMMAND_TOOLS`; `glab auth login -t/--token/-j/--job-token` values are redacted (Q56).

### 8.2 Egress (exfil-channel-guard, taint-escalation, network-egress-guard)

| Command | Egress |
|---|---|
| `glab snippet create\|new [files]` | `snippet`, judged exactly like `gist`: always asks, `allowed_hosts` never relaxes it |
| `glab issue\|mr create\|update --description-file F`, `--attach F`, `glab issue\|mr note … --attach F`, `glab release create\|upload … F` / `-F F`, `--template <path>` (a value that is absolute or has a path separator) | `body_file` |
| `gh\|glab api … --input F`, `-F k=@F`, `--field k=@F`, `--form k=@F` | `body_file` |
| `gh release upload`, `gh release create … <assets>`, `gh repo create --push`, `glab repo create`, fork remote repoints, CI-trigger file inputs | per the audit rows; `repo create --push` is also a push |
| `playbook forge … --body-file F` | `body_file` |

Hosts come from the command: `-R/--repo host/…`, `--hostname`, `GH_HOST` / `GITLAB_HOST` / `GL_HOST` / `GITLAB_URI` / `GITLAB_API_HOST` in the segment env or `ctx.env`, else the session's remotes snapshot (for `playbook forge`: the push remote). `github.com` is no longer hard-coded. The unparsed fallback `_RAW_EGRESS` gains `glab` and `playbook forge`. network-egress-guard gains forge-CLI host rows (precedent: `HF_ENDPOINT`).

### 8.3 Pushes (Q13)

`glab mr create|new` with `--fill` or `--push` (unless `--push=false`), `gh|glab repo create --push`, and GitLab's `-o merge_request.create` count as a push of `HEAD`'s branch for: the secret push scan, commit-convention, taint's push ask and `push_requires_green`. `push_requires_green` also fires on `glab mr create` and `playbook forge pr create`. Its reason says "pull request".

### 8.4 Push options (Q51)

One push-option judge in git_policy (always on), reading `-o` / `--push-option` and the `push.pushOption` config (on the `git -c`, `git config`, `GIT_CONFIG_*` and `.git/config` surfaces where `core.hooksPath` writes are judged):

| Option | Verdict |
|---|---|
| `secret_push_protection.skip_all`; a commit message with `[skip secret push protection]` | deny |
| `ci.variable=…`, `ci.input=…` | ask |
| `ci.skip`, `ci.no_pipeline`, `integrations.skip_ci` | ask |
| `merge_request.create` (+ `target`, `title`, `description`…) | a `pr create` (§8.3); `merge_request.description` is sent text |
| writing `push.pushOption` | judged with the rows above |

### 8.5 Other

- Remotes snapshot: stored URLs have userinfo stripped, and comparisons strip it on both sides (Q56).
- Unattended detection is unchanged (GitLab sets `CI=true`).
- Docs: `exfil-channel-guard/HOOK.md` names gists and snippets; `specs/prK-hook-pack.md` push and secret-path wording.

## 9. Hook-side constraints (from the layout refactor)

- F3 builds on A14/A15 (handler moves) and B4a/B4b (config reads through `HookConfig`); all four are done on integration as of 2026-10-21. Forge behaviour never rides in a move PR (L1, L13).
- New handler config keys are declared in `CONFIG_SCHEMA` and read through `HookConfig`; no raw `ctx.config.get(` (B4b's AST guard).
- Prefilters stay basename sets; no subcommand prefiltering.
- `safety/_egress` is private to `handlers.safety`; the audit and verify packs get forge knowledge from `forge/` or `judges/`.
- Logic shared by a guard and its CI twin (push scan, PR-title check, `.gitlab-ci.yml` removals) lives in `hook_runtime/judges/` or `forge/` (twins-use-judges).

## 10. GitLab CI (F5)

### 10.1 Recipe

README `## playbook ci` gains a `### GitLab CI` subsection (a second YAML block in its own subsection, so `test_readme_ci_snippet_passes_pr_title_only_through_env` keeps one block per section), mirrored in SPEC §12.11:

```yaml
playbook-ci:
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  variables:
    GIT_DEPTH: 0
    PLAYBOOK_PR_TITLE: $CI_MERGE_REQUEST_TITLE
  script:
    - git fetch origin "$CI_MERGE_REQUEST_TARGET_BRANCH_NAME"
    - playbook ci --base "${CI_MERGE_REQUEST_TARGET_BRANCH_SHA:-$CI_MERGE_REQUEST_DIFF_BASE_SHA}"
```

The base sits in the YAML, as on GitHub (Q53); `playbook ci` neither reads `CI_MERGE_REQUEST_*` nor fetches. Shell syntax targets Linux runners.

### 10.2 `playbook ci`

- `commands/twins/_git_scope.resolve_merge_base` exits 2 when the base equals `HEAD` or is not an ancestor of `HEAD` (forge-neutral, fail closed). `FETCH_DEPTH_HINT` names both `actions/checkout` `fetch-depth: 0` and GitLab `GIT_DEPTH: 0` plus the target-branch fetch.
- `_ci_commit_convention`: strip a leading `[Draft]`, `Draft:` or `(Draft)` (case-insensitive) from `PLAYBOOK_PR_TITLE` before `cz check --message`.

### 10.3 gate-scan (Q54)

In `hook_runtime/judges/_gate_weakening_files.removal_weakenings`, beside the `.github/workflows` rule; patterns only (the hook runtime may not import YAML):

- Files: `.gitlab-ci.yml` at any depth, `.gitlab/ci/**/*.y?ml`, and an extend-only `ci_config_globs` key in the gate-weakening policy table.
- Flagged when removed and not re-added in the same file, blocking like removed GitHub steps: top-level job keys (not global keywords `default`, `include`, `stages`, `variables`, `workflow`, `spec`, nor hidden `.jobs`), `script:` / `before_script:` / `after_script:` items, and `include:` entries (`local`, `template`, `component`, `project`, `remote`).
- The `playbook-ci` job (Q52): removing it, or adding `allow_failure: true`, `when: manual` or `when: never` to it, is flagged.

### 10.4 Making `playbook ci` a gate on GitLab (Q52)

README documents three levels: Free, "Pipelines must succeed" plus the CI configuration in a separate protected project (`.gitlab-ci.yml@group/ci-config`); Ultimate, a pipeline execution policy. It states that on Free an MR can otherwise edit its own pipeline.

## 11. Vendored plugin and docs

### 11.1 F6: mattpocock_skills "Forge issues"

Requires F4 (with its data-sending operations, hence F3), PR #158 merged, #157 on the same base, and a recorded amendment to specs/prT-mattpocock-skills.md D2, D13, D14 (and the triage note under D7), with every pinned test updated in the same PR (`NEW_TEXTS`, `REPLACED_TEXTS`, `LINE_COUNTS`, the reference inventory, gate G4's gh/glab ban, the ATTRIBUTIONS sentence "Only the local-markdown template ships").

- `setup-matt-pocock-skills`: a "Forge issues" option whose `docs/agents/issue-tracker.md` seed names only `playbook forge` operations. Setup runs `playbook forge which`; when a forge remote is detected it preselects "Forge issues" and the user confirms once (Q32). It runs `playbook forge auth status` and, on exit 2, shows the human step (Q34). It creates the configured labels on both forges with `label create` (Q42). The triage "PRs as a request surface" flag returns.
- The seed's sections: create / view / list / comment / label / close (`--reason`) / assign; one `Closes #n` line per ticket; wayfinding through `issue link-child`, `issue children`, `issue block`, `issue blockers`, with the text fallbacks (`Part of #map`, `Blocked by: #n`) on exit 3 (Q30, Q39); obsolete tickets closed as not-planned (Q44).
- wizard: the human-guided secret and variable steps cover GitLab CI/CD variables (Settings → CI/CD → Variables, masked/protected); discovery on GitLab reads `$NAME` / `${NAME}` in `.gitlab-ci.yml` and its includes, excluding predefined `CI_*`, `GITLAB_*`, `RUNNER_*`, `CHAT_*` (Q57).
- Wording: ask-matt ("each GitHub secret") and to-tickets ("GitHub, Linear, …") become forge-neutral.
- Every change gets an ATTRIBUTIONS.md entry. The superpowers plugin stays byte-faithful (its `gh api …/replies` line remains).

### 11.2 Docs touched across tickets

README: `forge` in `## Status`, a `playbook forge` section, the GitLab CI recipe and gate levels, the corrected "VCS token" claim, *Running on Domino Data Lab* (§13), GitLab Duo among `AGENTS.md` readers with a note that server-side agents need committed output (Q57). SPEC: a `### 12.N playbook forge` heading, §12.11 GitLab recipe, the gate-scan section, §11.5.3 after #158. MIGRATION.md module paths as the layout script requires.

## 12. Tickets and order (Q46, Q59)

A new tracker issue "Forge adapter: implementation tracker" lists F1 to F7. Tickets are squashed onto `integration/skills-and-layout` with the layout protocol (branch `forge/<ID>-<slug>`, Conventional Commit subject, body ending `Closes #N`). Work is written against integration paths; after every rebase run `python -m tests.architecture.module_moves apply` and `check`.

| Ticket | Content | Waits for | Machine |
|---|---|---|---|
| F0 | this spec, ADR 0003, CONTEXT terms (docs PR to `main`, like #73) | — | — |
| F1 | `forge/` package, contracts, `tests/forge/` | — | B |
| F2 | GitLab secrets (§7) | — | B |
| F3 | guards (§8) | F1 (refactor blockers N17–N21, A10, A11, B3, GC-1, A14, A15, B4a, B4b: done) | B |
| F4 | `playbook forge`, `[forge]`, core skill (§5, §6) | F1, F3 (B9: done) | A |
| F5 | GitLab CI (§10); GitLab CI variable names stay in `commands/twins/`, not `forge/` | — | A |
| F6 | plugin "Forge issues" (§11.1) | F4, #158, D2/D13/D14 amendment (#157 is on integration) | A |
| F7a | hardening without handler edits: `scanner-config-changed` gate rule, CI-detection tests (§14) | F5 (both edit `judges/_gate_weakening_files.py`) | A |
| F7b | hardening in handlers: token-printing block, `required_index`, `taint:forge`, `mail` egress (§14) | F1, F3 | B |

Status on 2026-10-21: every refactor ticket listed above is done on `integration/skills-and-layout`, which also contains `main` (#157). F1, F2 and F5 can start now in parallel; F3 and F7b follow F1; F7a follows F5; F4 follows F3; F6 follows F4 and #158. Re-check before starting: a ticket is done when integration has its `Closes #N` line (issues stay open until the final integration PR). F4 may not merge before F3: its data-sending operations would otherwise bypass exfil, git_policy, the push scan, network-egress and taint.

Gate per ticket, on Python 3.12 and 3.13: `ruff check --no-cache .`, `ruff format --check --no-cache .`, `mypy --cache-dir=/dev/null`, `pytest -q -p no:cacheprovider`. Modules stay near 500 lines (`commands/twins/ci.py` is at 488; `config/files.py` takes nothing).

## 13. Domino Data Lab

From Domino's Cloud docs (Release 94). The undocumented parts are confirmed by `domino-forge-check.sh`, a read-only, redacting check script that F4 ships in the README section *Running on Domino Data Lab*.

- Git-based project: the repo is at `/mnt/code`, with `origin` set to the URL the user entered (no Domino proxy). DFS project: attached repos at `/repos/<name>`; `/mnt` is not a clone. Imported repos at `/mnt/imported/code/<name>`.
- Detection is automatic for gitlab.com and hosts containing `gitlab`; other hosts need one committed `[forge] hosts` line. Domino's own provider type and credential domain live in Domino, not git config.
- Domino's stored Git credential is used to clone; `glab` cannot use it. Setup once per user: `glab` in the compute environment's Dockerfile (sudo is often unavailable and runtime installs do not reach jobs); `GITLAB_TOKEN` (`api`, `write_repository`) as a user environment variable (Vault-stored, injected into workspaces, jobs and apps); `coding-agent-playbook` in `requirements.txt`.
- Commit launches give a detached `HEAD` (§5.1). Domino's UI git actions run outside the agent; no guard sees them. One GitLab token per user environment (Q64); several instances need home persistence and `glab auth login` per host.

## 14. F7: hardening for both forges

- Commands that print forge tokens are blocked: `glab auth status -t/--show-token`, `glab config get token`, `gh auth token`, `printenv`/`echo` of `GITLAB_TOKEN`, `GITLAB_ACCESS_TOKEN`, `OAUTH_TOKEN`, `GH_TOKEN`, `GITHUB_TOKEN` (Q64).
- A forge-neutral `scanner-config-changed` gate rule over `.gitleaks.toml`, `.gitlab/secret-detection-ruleset.toml`, `.gitlab/sast-ruleset.toml`, `.github/secret_scanning.yml`; loosening patterns for `SAST_DISABLED`, `SECRET_DETECTION_DISABLED`, `*_EXCLUDED_PATHS` in CI files.
- `required_index` compares normalised URLs (no userinfo, lower-cased scheme and host, no trailing `/`).
- A `taint:forge` source: forge read operations (`gh`/`glab` issue|pr|mr view, `api`, `playbook forge` reads) mark the session.
- `git send-email` / `imap-send` (and `sendmail`, `msmtp`) as a `mail` egress kind.
- Tests for GitLab CI detection in `has_ci`, the resync trigger and the briefing probe.

## 15. Testing

- Fake `gh` and `glab` on `PATH` (Q24) record argv, stdin and environment and return canned JSON; no network and no real CLI in CI. Each operation has a GitHub and a GitLab case, plus exit-2/exit-3 cases.
- `tests/forge/`: host parsing (scp-like, ssh with port, https with userinfo), the §5.2 chain, `[forge]` entries with `api_host`, dialect tables pinned against the guard rows.
- Guards: GOLDEN rows for every §8.2 command on both forges; push-option rows; `playbook forge` rows; simulate-level tests where `glab snippet create notes.md` asks.
- Secrets: hit and miss rows per prefix; credential globs in `_SECRET`, `aliases.yml` in `_NOT_SECRET`.
- CI: FakeGit tests for the empty-range failure, draft stripping, gate-scan GitLab removals.
- Manual check before release: run the operations against a real GitHub repo and a real gitlab.com project, and run `domino-forge-check.sh` (redacting, read-only; checks `origin`, branch state, credential wiring, `glab`/`sudo` availability, API reachability) in a Domino workspace.

## 16. Open items for implementation

- Re-verify `gh`/`glab` flags against their manuals at the pinned minimums, GitLab token prefixes, and GitLab push options.
- `glab mr note create` is marked experimental; if it changes, `pr comment` falls back to `glab api …/notes` with the body from a file.
- Domino facts marked inferred (exact `origin` URL, credential wiring, job branch state) are confirmed by `domino-forge-check.sh`.
