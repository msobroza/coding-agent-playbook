---
status: accepted
---

# Release evals rerun only samples whose inputs changed

ADR 0012 has release metrics score every eval sample per harness and model target. Every `scripts/release.py prepare --eval` therefore reruns every sample on every target, even when nothing that decides its score changed: for v0.2.0 that is 105 paid harness runs, each graded by a paid judge. The metrics already record a `sample_digest` and a `prompt_digest` per sample, but nothing reads them to skip work, and they miss part of what decides a score: `prompt_digest` hashes the prompt's source, not the text of the rules it includes, and the judge's sample count, the judge CLI's version, fail-fast and the engine's scoring code are not recorded at all. A target without an endpoint also runs the harness and the judge with the maintainer's personal settings (CLAUDE.md, plugins, hooks, MCP servers), so its scores cannot be reproduced on another machine.

This record amends ADR 0012's release-metrics paragraph. A sample reruns only when its **inputs digest** differs from the baseline entry or the baseline has no entry for it. The inputs digest is the sha256 of the strict render of the prompt the sample sends (prompt body, the included rules' text, templating, prompt arguments) together with `sample_digest`, so a rule change fans out to exactly the samples whose prompt includes it, from any layer. Each release metrics file also records a **setup digest** of everything outside the samples that decides scores: the target (harness, harness version, model, endpoint fingerprint, small model), the run settings (runs, judge model, judge endpoint fingerprint, judge samples, the judge CLI's version, fail-fast), isolation, and a digest of the engine's scoring modules (checks, rubric compiler, scoring, runners, the judge and its prompt, the sample model and the release metrics fold). When any part differs from the baseline, every sample reruns and the record run prints which part changed (the file records every setup part, so the difference can be named again by comparing it with the baseline); rendering code needs no part of its own because the inputs digest hashes the rendered text. A new harness version is such a difference. Edition controls, the pinned samples graded on their frozen edition, always rerun, because they are the drift detectors. Every other sample becomes a **carried entry**: its baseline entry copied as recorded, without its old `vs_previous` and `accepted` keys, with `measured_in` naming the release and commit that measured it (kept from the baseline when the entry was already carried).

The engine does the selection: `playbook eval --run --all --record OUT --carry-from PREVIOUS.json` computes the digests, runs only what changed, copies the rest and writes one complete file, so it is testable without a release and usable outside one. `prepare --eval` is changed-only by default and passes the previous release's file for each target when there is one; `--full` reruns everything. A record run isolates the agent runner and the judge from personal settings with an empty temporary config directory, as routed runs already do; credentials come from `ANTHROPIC_API_KEY` or the target endpoint's `token_env`, the run is refused before the first paid call without either, and the file records the run as isolated.

Amended by ADR 0014: `--carry-from` also takes the releases directory, so a sample is carried from the newest committed metrics file with the same setup, whatever its release or target; a setup that differs only in the judge re-grades the stored answers instead of rerunning the agents.

## Considered Options

- **Select from the release manifest diff.** The manifest lists the graded set's digests, so it misses samples outside it, setup changes and rendering changes; the inputs digest decides per sample from what the agent actually receives, and the manifest diff stays for the notes.
- **A maximum carry age.** An entry carried for many releases is still exact as long as its inputs and setup digests match; forcing a rerun after N releases spends paid runs without new information, and the edition controls already catch drift.
- **Record a harness version change as a note only.** The harness changes what the agent does with the same text, so a score measured on another harness version is not comparable; the version is part of the setup digest and a change reruns everything.

## Consequences

- The summary of a release metrics file adds `rerun` and `carried` counts. `pass_rate` and `mean_score` cover all entries, so headline numbers stay comparable across releases; `cost_usd` and `tokens` cover only this release's fresh runs.
- The regression check gives carried entries the status `carried`, which never blocks, and the release pull request says "N rerun, M carried".
- A baseline without the inputs and setup digests reruns everything; there is no backfill. v0.2.0's metrics are recorded without them, so v0.3.0 is a full run and v0.4.0 is the first changed-only release.
- The harness updates about weekly, so most releases rerun fully until release runs pin a harness version; that pinning is later work and is what makes the savings real.
- Setup dependencies of a sample resolve at run time and stay out of the inputs digest; a committed lock file per sample is later work.
- Record runs no longer see the maintainer's CLAUDE.md, plugins, hooks or MCP servers, so their scores can be reproduced on another machine, and judge calls skip the slow start those settings caused.
