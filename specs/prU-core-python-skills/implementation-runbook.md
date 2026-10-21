# prU: implementation runbook

How prU is implemented, and how to resume after any interruption (a lost session, another machine, a failed wave). Decisions: [../prU-core-python-skills.md](../prU-core-python-skills.md). Tickets and waves: [tickets.md](tickets.md).

## Where everything is

| What | Where |
| --- | --- |
| Decisions D1-D79, defaults, follow-ups | `specs/prU-core-python-skills.md` |
| What to build, per skill | `specs/prU-core-python-skills/mapping-<skill>.md` |
| Every ticket, its waves and the content-ticket template | `specs/prU-core-python-skills/tickets.md` |
| Glossary and decision records | `CONTEXT.md`, `docs/adr/0001`-`0008` |
| Progress | GitHub tracker issue #176 (one checkbox per ticket), ticket issues #177-#263 |
| Integrated work | branch `integration/core-python-skills` |
| One ticket's work before integration | branch `ticket/<id>` (for example `ticket/L0-01`) |

The mapping and ticket files were generated from verified mapping data during design. From now on they are the source of truth and are edited by hand: a scope change updates the spec's decision list, `tickets.md` and the affected mapping file in the same commit, and a new ticket gets a GitHub issue that the tracker lists.

## How a wave runs

Waves run in the order of the wave table in `tickets.md` (0, 0b, 1-9). Wave N+1 starts only after wave N is integrated and its gate is green.

1. **Implement.** Each ticket runs in its own fresh-context agent, in an isolated git worktree, at medium effort, with the text of the `/mattpocock-skills:implement` skill plus the ticket's issue body. At most three tickets run at once, because the machine has about 8 GB of RAM and little free disk. The agent:
   - starts from the integration tip: `git fetch origin integration/core-python-skills && git checkout -B ticket/<id> origin/integration/core-python-skills`;
   - works test-first at the seams (`/tdd`), runs type checks and single test files regularly, and runs the test directories it touches plus `pytest -m catalog`;
   - runs `/code-review` (its Standards and Spec review agents) and fixes every real finding;
   - commits with a Conventional Commits subject equal to the ticket title, the body ending `Refs: #<issue> (prU <id>)`;
   - pushes with `git push origin HEAD:refs/heads/ticket/<id>`.
2. **Integrate.** One integrator agent, also isolated, then:
   - squash-merges each pushed ticket branch into `integration/core-python-skills` as one commit `<ticket title> (#<issue>)` whose body ends `Closes #<issue>`;
   - runs the full CI-parity gate once for the wave: `ruff check .`, `ruff format --check .`, `mypy`, the full `pytest` with CI's coverage options, and the commit-convention check;
   - fixes failures with small `fix:` commits, or records pre-existing ones;
   - pushes fast-forward only: `git push origin HEAD:refs/heads/integration/core-python-skills`;
   - removes the merged tickets' local worktrees to free disk.
3. **Record.** The orchestrator ticks the wave's boxes in tracker #176 and comments with the integration head and the gate result.

The `Closes #N` lines close each issue only when the final PR merges into `main`; until then, the tracker's checkboxes are the progress record.

## House rules for every commit

- Authored by the repository owner as configured locally. No `Co-Authored-By` or other trailers, no `--author`, no signing, no change to `git config`.
- Conventional Commits subjects; the repo's commitizen check enforces them.
- Never commit harness files: `CLAUDE.md`, `.claude/`, `AGENTS.md`, `.opencode/`, `.agents/`, `shared_skills/`, `.mcp.json`.
- No push to `main`, no force-push. CI runs only on the final PR into `main`.
- Tests and probes use a shared virtual environment with the worktree's own sources first (`PYTHONPATH=$PWD/src`); never create one virtual environment per ticket.

## Resuming after an interruption

1. **Read the state.**
   - Tracker: `gh issue view 176 --repo msobroza/coding-agent-playbook`.
   - Integrated tickets: `git fetch origin && git log --oneline origin/main..origin/integration/core-python-skills`. Every squash commit ends with `(#<issue>)`.
   - Pushed but not integrated: `git ls-remote origin 'refs/heads/ticket/*'`, minus the tickets already squash-merged.
2. **Classify each ticket of the lowest unfinished wave.**
   - *Integrated*: its squash commit is on the integration branch. Tick its box if it is not ticked.
   - *Pushed, not integrated*: its `ticket/<id>` branch exists. Rerun only the integrate step for it.
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
