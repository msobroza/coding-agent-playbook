---
status: proposed
---

# Releases publish their metric changes, and record runs reuse every committed result

ADR 0013 lets a record run reuse a sample only from the previous release's metrics file of the same target. So a result measured earlier with the same task, model, parameters and sample is paid for again. That happens when it came from an older release, under another target name, or before a setup changed and changed back. The release itself publishes nothing: CI tags the commit, and the metrics stay in JSON files that nobody reads to see how a task's scores moved.

This record amends ADR 0013's reuse rule. `--carry-from` also accepts the releases directory. The record then indexes every committed metrics file whose setup matches this run's, whatever its target name. A sample whose inputs digest is found there becomes a carried entry from the newest release that measured it. Edition controls still always rerun, a setup difference still reruns every sample, and `--carry-from FILE` keeps its meaning. The regression check still compares with the previous release's file. An entry carried from an older release whose inputs differ from that file's entry is compared like a rerun, never waved through as `carried`, so reverting to older text cannot hide a regression.

Each release also publishes a metric-change bundle on GitHub and on GitLab: a change report (also the release description), a CSV of every release's entries, the release's metrics files, and charts of per-task deltas, per-sample deltas and trends across releases. The engine computes the report from the committed files with the release gate's own verdicts. A script adds the charts, and CI jobs on the release tag build the bundle and attach it to the forge's release. The maintainer still runs the paid evals, so CI holds no model key and no harness CLI.

## Considered Options

- **CI runs the evals.** Release numbers would come from one known machine, but CI would need model keys and both harness CLIs, plus hours of runner time per release. The setup digest already makes a maintainer's isolated run reproducible.
- **A result store outside the releases, fed by benchmarks and ad-hoc runs.** More reuse, but a second source of truth whose entries no release reviewed. The committed metrics files are already reviewed in release pull requests.
- **Commit the bundle in the release pull request.** The charts would be reviewable before merging, but binary files would enter git every release, and a report fix could not be republished without a new release. The release pull request carries the Markdown report instead, and CI rebuilds the bundle from the same files.

## Consequences

- A release reruns only the samples whose inputs no committed release measured under the same setup. The plan line names the release and target each carried entry comes from.
- A carried entry can come from any earlier release. `measured_in` stays the provenance, and the regression check notes `measured in <release>` when it compares one.
- GitHub publishes from the tagging workflow, because a tag pushed with `GITHUB_TOKEN` starts no other workflow. GitLab publishes on `v*` tag pipelines. Rerunning either job updates the release instead of failing. A manual trigger backfills v0.2.0 to v0.4.0.
- matplotlib is installed only in the publish jobs, never as an engine dependency.
