# prU runner

Tooling that implements the prU tickets with coding agents, on one or two machines. It is temporary: F-02 deletes this directory before the final PR into `main`.

| File | Role |
| --- | --- |
| `prU-runner.js` | The workflow script. It runs a list of tickets in dependency order. Each ticket is implemented, reviewed by the code-review skill's two sub-agents, fixed, then squash-merged into `integration/core-python-skills` with a light gate. With `fullGate`, it runs the chunked full suite instead. |
| `plan.py` | Builds the runner's arguments and reports ticket status, from `tickets.md`, `ticket-issues.json`, `assignment.json` and the commits on `origin`. |
| `assignment.json` | Which machine owns which ticket. Never run a ticket on both machines. |
| `ticket-issues.json` | Ticket id to GitHub issue number, and the tracker issue. |
| `tools/overlay-venv.sh` | A pip-less test interpreter per worktree (see "Test interpreters" in the runbook). |
| `tools/suite_chunk.py` | The full suite as 12 chunks under the 10-minute command limit. |

## One machine's loop

From the repository root of this machine's checkout, on `integration/core-python-skills`:

```bash
python3 specs/prU-core-python-skills/runner/plan.py status --machine B
```

```bash
python3 specs/prU-core-python-skills/runner/plan.py args --machine B --parallel 6 --scratch /abs/scratch --shared-venv /abs/venv > /abs/scratch/args-B.json
```

Then start the Workflow tool with `scriptPath` set to the absolute path of `prU-runner.js` in this checkout, and `args` set to the JSON object in `args-B.json`. The JSON is passed as an object, not as a string.

When the run returns:

- **`integrated`**: done. Refresh the tracker: fetch its body with `gh issue view 176 --repo msobroza/coding-agent-playbook --json body -q .body > now.md`, run `plan.py tracker-body --current now.md > new.md`, then `gh issue edit --repo msobroza/coding-agent-playbook 176 --body-file new.md`. Keep `--repo` first: the allow rules match the command's beginning. This is idempotent, so either machine can run it.
- **`blocked`**: the ticket waits for a ticket of the other machine. Poll `plan.py status --machine B` every 15 minutes and start a new run when tickets become ready.
- **`failed`**: read the run's journal, then fix the ticket by hand or rerun it with `plan.py args --only <id>`.
- **Cleanup**: run `plan.py cleanup` (a dry run), then `plan.py cleanup --apply`, only when no run is active on this machine; right after a run ends, add `--idle-minutes 0`. Changes that already exist in a pushed commit count as nothing to lose: an implementer's worktree shows them when the fix agent pushes the ticket from elsewhere.

`--parallel` is the number of tickets in flight at once. Use 2 on an 8 GB machine, and 6–8 with 32 GB of RAM and 10 or more cores. The workflow itself runs at most min(16, cores - 2) agents at once.

## The last steps (machine A)

1. Once every ticket but F-02 is integrated, run `plan.py args --full-gate ...` and start the runner: the full suite runs on the integration tip.
2. Then F-02, by the orchestrator with the owner: final checks, delete this directory, and open the one PR into `main`.
