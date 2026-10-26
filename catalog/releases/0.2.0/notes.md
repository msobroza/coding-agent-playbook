# Release 0.2.0

Changes since 0.1.0.

## Breaking changes

- #326: the v2 prompts become the current text. A config that sets `prompts` fails to load; delete the line. The eval flags `--prompt-set` and `--base-prompt-set` are removed. A layer's `prompts/v2/` is refused by `playbook validate`.

## Changed artifacts

All nine core prompts now hold the former v2 text. Their ids, names and slash commands are unchanged. Five of them moved from `.md` to `.md.j2`, so the generated diff showed them as removed and added; they were not.

- prompt `characterize`
- prompt `explain`
- prompt `find-injected-vulnerability`
- prompt `generate-tests`
- prompt `make-testable`
- prompt `refactor`
- prompt `review`
- prompt `review-architecture`
- prompt `security-review`

## Release metrics

`claude-opus` (Claude Code 2.1.292, `claude-opus-5-5`, 3 runs per sample, judged by `claude-opus-5-5`): 35 samples, pass rate 0.962. This is the first recorded release, so there is no previous release to compare with.

The runs were isolated from personal Claude Code settings. Seven samples were rerun on the same base commit: `characterize/legacy-pricing`, `generate-tests/async-code`, `generate-tests/edge-cases`, `generate-tests/happy-path`, `make-testable/inject-clock`, `refactor/extract-helper` and `refactor/rename-for-clarity`. Their first recording had no edit permission, and 18 of their runs had file writes denied. The rerun accepted edits and allowed read and search tools plus git, python, pytest, uv and ls. The other 28 samples keep their first-run entries: none of their 84 runs had a denied tool call. The metrics file lists the rerun samples under `rerun_samples`.

## Pull requests

- #321
- #323
- #324
- #325
- #326
- #328
