---
id: playbook-creator
name: playbook-creator
description: "Conventions for authoring playbook content."
playbook:
  use_when: "editing catalog/, playbook/ or an overlay's resources/"
  files: "Playbook content in catalog/, playbook/ or an overlay's resources/"
  sections:
    - id: layers
      title: "Layers"
      impact: CRITICAL
      summary: "Each artifact lives in one layer's kind directory, and a later layer replaces an earlier one by id."
      open_when: "Deciding which layer and directory a new file goes in, or reusing an id that core, a plugin or an overlay ships."
    - id: rules
      title: "Rules"
      impact: CRITICAL
      summary: "A rule file carries the engine's frontmatter, a stable id, a gate and one topic within 100 lines."
      open_when: "Writing or editing a rule file's frontmatter, id, applies_if, globs, Jinja branch or body text."
    - id: validation
      title: "Validation"
      impact: CRITICAL
      summary: "Every source change passes playbook validate; generated files change only through sync."
      open_when: "Before finishing or committing a playbook change, or when validate, sync --check, docs-check or a catalog test fails."
    - id: skills
      title: "Skills"
      impact: HIGH
      summary: "A skill declares ordered sections and lists every file it ships; the engine writes its index."
      open_when: "Creating a skill, editing a SKILL.md or its playbook block, or adding a guide, script or example to a skill."
    - id: hooks
      title: "Hooks"
      impact: HIGH
      summary: "A hook declares what it may decide, runs a registered or trusted handler and degrades to guardrail text."
      open_when: "Creating or editing a HOOK.md: its events, matcher, handler, decisions, timeout, summary line or guard twin."
    - id: prompts
      title: "Prompts and eval samples"
      impact: HIGH
      summary: "A prompt names the rules it needs by id, and its eval samples prove what it must achieve."
      open_when: "Creating or editing a slash-command prompt, or an eval sample's task file, setup/, solution/ or negatives."
    - id: plugins
      title: "Plugins and overlays"
      impact: MEDIUM
      summary: "Plugins are pure content, overlays are importable packages, and third-party text keeps its license and change list."
      open_when: "Creating a bundled plugin or an overlay package, marking a framework, or bringing in third-party text or ideas."
---

# Playbook creator

This skill is for adding or changing playbook content: rules, skills, hooks, prompts, eval samples, bundled plugins and overlays. It serves four layers, merged in this order: the engine's `catalog/core/`, a bundled plugin under `catalog/plugins/<name>/`, an overlay package's `resources/` directory, and a consumer repo's own `playbook/` (start one with `mkdir playbook`). Every layer has the same kind layout, so a file's path says what it is. Content reaches an agent only through sync, which renders each layer's sources into the generated harness files.

## Quick reference

Where each kind lives, inside any layer root:

| Kind | Path |
| --- | --- |
| Always rule | `rules/<file>.md` (core: `rules/always/NN-<id>.md`) |
| Rule joining another layer's skill | `rules/<id>.md` with `skill:` and `section:` |
| Member rule | `skills/<skill>/rules/<id>.md` or `.md.j2` |
| Skill | `skills/<id>/SKILL.md`, with `references/`, `scripts/`, `examples/` |
| Prompt | `prompts/<id>.md` or `.md.j2` |
| Hook | `hooks/<category>/<id>/HOOK.md` |
| Eval sample | `eval_samples/<id>/` beside the layer's `prompts/` |

The loop after every edit:

```bash
playbook validate                  # one FAIL line per error, or OK
playbook render <id> --show-source # the rendered artifact and its source
playbook check                     # this repo's facts and why an artifact is skipped
playbook sync                      # the user runs it, or [hooks] auto_sync does
playbook sync --check              # the working copy matches the sources
playbook docs-check                # links and code blocks before committing Markdown
```

Never edit generated output (`.claude/`, `.opencode/`, `.agents/`, `.continue/`, `AGENTS.md`): sync overwrites it. Edit the source, validate, then sync.

## See also

- playbook-guardrails: the guardrail text of every enabled hook.
- python-tooling: formatting the Python code blocks inside Markdown.
