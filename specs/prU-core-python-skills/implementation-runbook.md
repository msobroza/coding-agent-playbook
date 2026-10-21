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

The mapping and ticket files were generated from verified mapping data during design. From now on they are the source of truth and are edited by hand: a scope change updates the spec's decision list, `tickets.md` and the affected mapping file in the same commit, and a new ticket gets a GitHub issue that the tracker lists.

## How a wave runs

Waves run in the order of the wave table in `tickets.md` (0, 0b, 1-9). Wave N+1 starts only after wave N is integrated and its gate is green.

1. **Implement.** Each ticket runs in its own fresh-context agent, in an isolated git worktree, at medium effort, with the text of the `/mattpocock-skills:implement` skill plus the ticket's section of `tickets.md`. At most three tickets run at once, because the machine has about 8 GB of RAM and little free disk. The agent:
   - starts from the integration tip: `git fetch origin integration/core-python-skills && git checkout -B ticket/<id> origin/integration/core-python-skills`;
   - creates its test interpreter (see "Test interpreters" below);
   - works test-first at the seams (`/tdd`), runs type checks and single test files regularly, and runs the test directories it touches plus `pytest -m catalog`; it never runs the full suite;
   - commits with a Conventional Commits subject equal to the ticket title, the body ending `Refs: #<issue> (prU <id>)`;
   - pushes with `git push origin HEAD:refs/heads/ticket/<id>`.
2. **Review.** Two more fresh-context agents read the pushed diff (`git diff origin/integration/core-python-skills...origin/ticket/<id>`), read-only. They are the two axes of `/code-review`: *Standards* (the repo's conventions, `CONTEXT.md`, the ADRs, the clean-code rules) and *Spec* (every acceptance criterion and decision). They run as separate agents because an agent inside a workflow cannot start agents of its own.
3. **Fix.** When the reviewers report findings, one more agent applies the real ones (or says why it rejects one), reruns the touched tests and pushes the ticket branch again.
4. **Verify.** A fresh agent checks out the pushed branch, decides every acceptance criterion with evidence (the command it names, the test that proves it, or the code line), checks the listed files, the scope and the commit rules, and runs ruff, mypy and the touched test directories. When something is unmet, a fix agent repairs it and the verifier runs again, for at most two repair rounds. A ticket that is still unverified stays out of the integration and goes back to the orchestrator.
5. **Integrate.** One integrator agent, also isolated, then:
   - squash-merges each verified ticket branch (still at the verified commit) into `integration/core-python-skills` as one commit `<ticket title> (#<issue>)` whose body ends `Closes #<issue>`;
   - runs the full CI-parity gate once for the wave: `ruff check .`, `ruff format --check .`, `mypy`, the full `pytest` in chunks (see "The full suite in chunks" below), and the commit-convention check;
   - fixes failures with small `fix:` commits, or records pre-existing ones;
   - pushes fast-forward only: `git push origin HEAD:refs/heads/integration/core-python-skills`;
   - removes the merged tickets' local worktrees to free disk.
6. **Record.** The orchestrator ticks the wave's boxes in tracker #176 and comments with the integration head and the gate result.

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

The full suite takes about 21 minutes, longer than the 10 minutes one agent command may run. The integrator runs it as directory groups, one command each. The first group erases the coverage data and every later one appends to it (`--cov-append`, report and `fail-under` off), with `COVERAGE_FILE` outside the worktree. A last `coverage report --fail-under=80` on the combined data applies CI's threshold. Every directory under `tests/` belongs to exactly one group, so a new test directory must be added to a group. The groups, which cover all 11,510 tests once (counted at 45af894c):

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

## House rules for every commit

- Authored by the repository owner as configured locally. No `Co-Authored-By` or other trailers, no `--author`, no signing, no change to `git config`.
- Conventional Commits subjects; the repo's commitizen check enforces them.
- Never commit harness files: `CLAUDE.md`, `.claude/`, `AGENTS.md`, `.opencode/`, `.agents/`, `shared_skills/`, `.mcp.json`.
- No push to `main`, no force-push. CI runs only on the final PR into `main`.
- Tests and probes use the shared virtual environment through the worktree's pip-less overlay (see "Test interpreters"); never install packages into a new environment per ticket.

## Resuming after an interruption

1. **Read the state.**
   - Tracker: `gh issue view 176 --repo msobroza/coding-agent-playbook`.
   - Integrated tickets: `git fetch origin && git log --oneline origin/main..origin/integration/core-python-skills`. Every squash commit ends with `(#<issue>)`.
   - Pushed but not integrated: `git ls-remote origin 'refs/heads/ticket/*'`, minus the tickets already squash-merged.
2. **Classify each ticket of the lowest unfinished wave.**
   - *Integrated*: its squash commit is on the integration branch. Tick its box if it is not ticked.
   - *Pushed, not integrated*: its `ticket/<id>` branch exists. Rerun only the integrate step for it.
   - *Committed locally, not pushed*: its commits sit in a leftover worktree. Each session may write only inside its own worktree, so to finish such a ticket by hand, check that the leftover worktree is clean, remove it (`git worktree remove <path>`; the commits stay on `ticket/<id>`), check the branch out in your own worktree, finish it, and push.
   - *Lost or never started*: nothing pushed. Discard any local leftover (`git worktree list`, then `git worktree remove --force <path>`; delete the local `ticket/<id>` branch) and rerun its implement step from the integration tip.
3. **Never skip a wave.** Finish and integrate the lowest unfinished wave, gate green, before starting the next.
4. **On a new machine,** first:
   - clone the repo and check out `integration/core-python-skills`;
   - create one virtual environment with the dev extra (`uv venv` then `uv pip install -e ".[dev]"`, or the project's documented setup);
   - log in with `gh auth login`;
   - set your git identity;
   - add the project-local allow rules (`.claude/settings.local.json`, never committed) that agents need to proceed unattended: `gh issue create`, `gh issue edit` and `gh issue comment` on `msobroza/coding-agent-playbook`, the Workflow tool, `git push origin HEAD:refs/heads/ticket/*`, and `git push origin HEAD:refs/heads/integration/core-python-skills`.
5. **Hand the work to an agent** with: "Continue prU: read `specs/prU-core-python-skills/implementation-runbook.md`, then the tracker #176, and resume from the lowest unfinished wave with the wave procedure in the runbook."

## Finishing

- **Wave 8 (F-01)** adds the opt-in eval comparison (D37). It is implemented, not run: a paid run needs the owner's credentials and approval.
- **Wave 9 (F-02)** runs the full gate on Python 3.12 and 3.13 and opens the one PR from `integration/core-python-skills` into `main`. The owner reviews and merges it; agents never merge.
- After the merge, the follow-ups listed in the spec start as separate work.
