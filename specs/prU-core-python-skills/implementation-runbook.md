# prU: implementation runbook

How prU is implemented, and how to resume after any interruption (a lost session, another machine, a failed wave). Decisions: [../prU-core-python-skills.md](../prU-core-python-skills.md). Tickets and waves: [tickets.md](tickets.md).

## Where everything is

| What | Where |
| --- | --- |
| Decisions D1-D80, defaults, follow-ups | `specs/prU-core-python-skills.md` |
| What to build, per skill | `specs/prU-core-python-skills/mapping-<skill>.md` |
| Every ticket, its waves and the content-ticket template | `specs/prU-core-python-skills/tickets.md` |
| Glossary and decision records | `CONTEXT.md`, `docs/adr/0001`-`0008` |
| Progress | GitHub tracker issue #176 (one checkbox per ticket), ticket issues #177-#263 and #264 (L0-27, D80) |
| Integrated work | branch `integration/core-python-skills` |
| One ticket's work before integration | branch `ticket/<id>` (for example `ticket/L0-01`) |
| The runner, the planner and the machine split (temporary, deleted by F-02) | `specs/prU-core-python-skills/runner/` |

The mapping and ticket files were generated from verified mapping data during design. From now on they are the source of truth and are edited by hand: a scope change updates the spec's decision list, `tickets.md` and the affected mapping file in the same commit, and a new ticket gets a GitHub issue that the tracker lists.

## How tickets run

Waves 0-2 ran wave by wave. From wave 3 on, tickets run in dependency order with the runner in [runner/](runner/README.md): a ticket starts as soon as every ticket it depends on is integrated, and it is integrated as soon as it is done. The wave table in `tickets.md` stays as the original grouping. The dependencies come from each ticket's "depends on" line and the content table; `runner/plan.py` reads them, checks there is no cycle, and builds a run's arguments.

The owner chose speed: no separate verify step and no full suite per ticket. Wave 1 ran with both, an acceptance verifier with repair rounds and the chunked full suite; the full suite now runs once, after the last ticket.

1. **Implement.** Each ticket runs in its own fresh-context agent, in an isolated git worktree, at medium effort, with the text of the installed `/mattpocock-skills:implement` skill plus the ticket's section of `tickets.md`. The skill's own last steps are replaced: the agent does not run the full suite and does not run `/code-review` itself (see step 2). The agent:
   - starts from the integration tip (`git checkout -B ticket/<id> origin/integration/core-python-skills`), or from its existing `ticket/<id>` branch after an interrupted run, merging the tip into it;
   - creates its test interpreter (see "Test interpreters" below);
   - works test-first at the seams (`/tdd`), runs type checks and single test files regularly, and runs the test directories it touches, `pytest -m catalog` for catalog changes and `tests/unit` for doc changes;
   - commits with a Conventional Commits subject equal to the ticket title, the body ending `Refs: #<issue> (prU <id>)`;
   - pushes with `git push origin HEAD:refs/heads/ticket/<id>`.
2. **Review.** The `/mattpocock-skills:code-review` skill, run as its two parallel sub-agents: *Standards* (the repo's documented standards plus the skill's smell baseline) and *Spec* (the ticket's issue, its section of `tickets.md` and the decisions it cites). Each sub-agent receives the skill's full text, a header that names its role, and the inputs of the skill's steps 1-3: the fixed point `origin/integration/core-python-skills`, `origin/ticket/<id>` as `HEAD`, the spec source and the standards files. The workflow plays the skill's lead: an agent inside a workflow cannot start sub-agents, so the workflow starts both and keeps their reports apart (step 5). The repo has no `docs/agents/issue-tracker.md`; the header points the Spec sub-agent at `gh issue view`.
3. **Fix.** When the reviewers report findings, one more agent fixes every hard violation and every Spec finding, applies a judgement-call smell when it clearly helps, rejects wrong findings with a reason, reruns the touched tests and pushes the ticket branch again.
4. **Integrate.** One integrator agent per ticket, one at a time per machine:
   - squash-merges `ticket/<id>` into `integration/core-python-skills` as one commit `<ticket title> (#<issue>)` whose body ends `Closes #<issue>`; `tests/cli/golden/cli_surface.json` is re-recorded, never merged by hand;
   - runs a light gate: `ruff check .`, `ruff format --check .`, plain `mypy` (no path argument: `mypy .` also checks the `catalog/` eval-sample fixtures and fails on them), and the test directories the commit touches, with `pytest -m catalog` and `tests/unit` as in step 1;
   - pushes fast-forward only; when the other machine pushed first, it rebases its one commit, reruns the gate and pushes again;
   - removes the ticket's clean worktrees.
5. **Record.** After a run, the orchestrator refreshes tracker #176 with `plan.py tracker-body` (it ticks every integrated ticket, so it is safe to run from either machine).

At most `--parallel` tickets are in flight per machine: 2 on the 8 GB machine, 6-8 on a machine with 32 GB of RAM and 10 or more cores.

### Test interpreters

All worktrees share one virtual environment, and its editable install points at one checkout's `src`. Setting `PYTHONPATH=$PWD/src` is not enough: hook tests start `python -I -m coding_agent_playbook.hook_runtime`, and `-I` ignores `PYTHONPATH`, so those subprocesses would import the other checkout's code. Each worktree therefore gets a pip-less overlay (about 44 KB) whose own `site-packages` holds three path files, read in this order:

```bash
python3.13 -m venv --without-pip <overlay>
echo "$PWD/src" > <overlay>/lib/python3.13/site-packages/00_src.pth
echo "<shared venv>/lib/python3.13/site-packages" > <overlay>/lib/python3.13/site-packages/01_shared.pth
cp <shared venv>/lib/python3.13/site-packages/a1_coverage.pth <overlay>/lib/python3.13/site-packages/
```

Run pytest with `<overlay>/bin/python -m pytest`; `mypy` and `ruff` keep using the shared environment with `PYTHONPATH=$PWD/src`. Check that `<overlay>/bin/python -I -c "import coding_agent_playbook; print(coding_agent_playbook.__file__)"` prints a path inside the worktree.

### The full suite in chunks

The full suite takes about 21 minutes, longer than the 10 minutes one agent command may run. The final gate runs it as numbered directory groups, one command each, through `runner/tools/suite_chunk.py`, which holds the group table (so commands carry no globs or shell variables, which the worktree guard rejects):

- `check` collects the suite and fails when a test file is in no group or in several, so a new test directory must be added to a group;
- group 1 erases the coverage data and every later group appends to it (`--cov-append`, report and `fail-under` off);
- `report` applies CI's `--fail-under=80` to the combined data, counting only `src/`.

The data stays in `./.coverage` at the worktree root, as in CI. Exporting `COVERAGE_FILE` to keep it elsewhere broke wave 1's first run: the nested pytest runs some tests start inherit it and overwrite the combined data. The groups, which covered all 11,510 tests once at 45af894c (443 test files after wave 1):

| Chunk | Paths | Tests |
| --- | --- | --- |
| 1 | `tests/adapters tests/agent_harness tests/architecture tests/artifacts tests/catalog` | 1,149 |
| 2 | `tests/cli/test_[a-r]*.py` | 488 |
| 3 | `tests/cli/test_[s-z]*.py` | 509 |
| 4 | `tests/config tests/detector tests/evals tests/generated_output` | 995 |
| 5 | `tests/grading tests/hooks` | 934 |
| 6 | `tests/hook_runtime/handlers` | 1,175 |
| 7 | `tests/hook_runtime/dispatch tests/hook_runtime/harness tests/hook_runtime/config` | 819 |
| 8 | `tests/hook_runtime/{shell,judges,state,diagnostics,stop,git} tests/hook_runtime/test_*.py` | 896 |
| 9 | `tests/integration` | 703 |
| 10 | `tests/lockfile tests/metrics_gate tests/rendering tests/security tests/skills tests/sync tests/validation` | 923 |
| 11 | `tests/plugins` | 1,928 |
| 12 | `tests/unit` | 991 |

The CLI tests are the slowest per test, which is why they get two small chunks. When the machine swaps heavily, everything runs several times slower; a chunk that hits the limit is split further and only its parts are rerun.

The `Closes #N` lines close each issue only when the final PR merges into `main`; until then, the tracker's checkboxes are the progress record.

## Two machines

Two machines can implement tickets at the same time, each on its own share. `runner/assignment.json` gives each ticket to machine A or B (content tickets by skill lane), and each machine runs only its own share. Only the `web-application`, `python-testing` and `python-architecture` content tickets depend on another lane, so they stay together on one machine; the other machine's tickets then wait only for engine tickets.

- Each machine integrates its own tickets into the one integration branch, with fast-forward pushes; the integrator rebases and retries when the other machine pushed first.
- A ticket that waits for one of the other machine's tickets comes back as `blocked`; poll `plan.py status --machine <M>` and start a new run once it is ready.
- Both machines refresh the tracker with `plan.py tracker-body`, which ticks from the integration branch, so concurrent refreshes converge.
- Moving work between machines is a commit to `assignment.json`; a ticket never runs on both.
- Machine A runs the full gate and F-02 at the end.
- Both machines use the owner's account, so they share its rate limits.

## House rules for every commit

- Authored by the repository owner as configured locally. No `Co-Authored-By` or other trailers, no `--author`, no signing, no change to `git config`.
- Conventional Commits subjects; the repo's commitizen check enforces them.
- Never commit harness files: `CLAUDE.md`, `.claude/`, `AGENTS.md`, `.opencode/`, `.agents/`, `shared_skills/`, `.mcp.json`.
- No push to `main`, no force-push. CI runs only on the final PR into `main`.
- Tests and probes use the shared virtual environment through the worktree's pip-less overlay (see "Test interpreters"); never install packages into a new environment per ticket.

## Resuming after an interruption

1. **Read the state** from the repository root: `python3 specs/prU-core-python-skills/runner/plan.py status --machine <A|B>`. It lists the machine's tickets as integrated, ready or waiting (with what they wait for), and flags a ticket whose `ticket/<id>` branch is pushed but not integrated.
2. **Clean up leftovers** when no run is active on this machine: `plan.py cleanup` (a dry run), then `plan.py cleanup --apply`. It removes only workflow worktrees that are idle for an hour, clean and pushed. A leftover with uncommitted changes is either stale, superseded by its pushed branch, or unpushed work. To finish unpushed work by hand, remove the worktree (its commits stay on `ticket/<id>`), check the branch out in your own worktree, finish it and push: each session may write only inside its own worktree.
3. **Start a run** with `plan.py args --machine <M> ...` and the runner (see `runner/README.md`). It skips integrated tickets, continues a pushed `ticket/<id>` branch instead of restarting it, and starts each ticket once its dependencies are integrated.
4. **A stopped run** can be resumed with the Workflow tool's run id and the same arguments. It reuses finished agents only up to the first agent call whose start order changed, so some agents run again. That is harmless, because they read the pushed branches, but it costs time. Starting a fresh run from `plan.py args` is just as safe.
5. **On a new machine,** first:
   - clone the repo and check out `integration/core-python-skills`;
   - create one virtual environment with the dev extra from a native Python (an x86_64 Python on Apple silicon runs every test under Rosetta): `uv venv --python 3.13` then `uv pip install -e ".[dev]"`;
   - install the mattpocock-skills plugin in Claude Code (the runner reads its `implement` and `code-review` skills);
   - log in with `gh auth login`, and set your real git identity (`git config user.name` and `user.email`);
   - add the project-local allow rules (`.claude/settings.local.json`, never committed) that agents need to proceed unattended: `gh issue create`, `gh issue edit` and `gh issue comment` on `msobroza/coding-agent-playbook`, the Workflow tool, `git push origin HEAD:refs/heads/ticket/*`, and `git push origin HEAD:refs/heads/integration/core-python-skills`.
6. **Hand the work to an agent** with: "Continue prU as machine <M>: read `specs/prU-core-python-skills/implementation-runbook.md` and `specs/prU-core-python-skills/runner/README.md`, run `plan.py status --machine <M>`, and run your ready tickets with the runner until your share is integrated."

## Finishing

- **F-01** adds the opt-in eval comparison (D37). It is implemented, not run: a paid run needs the owner's credentials and approval.
- **The full gate** runs once every ticket but F-02 is integrated: `plan.py args --full-gate ...` and the runner, on machine A.
- **F-02** deletes `runner/`, runs the full gate on Python 3.12 and 3.13 and opens the one PR from `integration/core-python-skills` into `main`. The owner reviews and merges it; agents never merge.
- After the merge, the follow-ups listed in the spec start as separate work.
