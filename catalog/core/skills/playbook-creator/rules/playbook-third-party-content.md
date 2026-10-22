---
id: playbook-third-party-content
name: Third-party content
description: "Vendor third-party text only under its license, with byte-identical license copies and a change list, or distill the ideas in your own words."
version: 1
scope: scoped
globs:
  - "catalog/**/ATTRIBUTIONS.md"
  - "catalog/**/LICENSE*"
  - "src/*/resources/**/ATTRIBUTIONS.md"
  - "playbook/**/ATTRIBUTIONS.md"
applies_if:
  playbook_layer: true
section: plugins
priority: 61
tags: [playbook, plugins, licensing]
---

# Vendor with the license and a change list, or distill in your own words

## Description

Third-party material enters a layer in one of two ways.

**Vendored:** text copied and adapted, only under a license that allows it.

- The upstream license ships byte-identical: `LICENSE` at a plugin root, and a copy in every synced skill directory that holds the text (`LICENSE` in a plugin skill's references directory, `LICENSE.<source-slug>` in each core skill).
- `ATTRIBUTIONS.md` records the source, its version or tag, the commit pin, the author, the license and every change per file.
- In core, it holds one mapping table per source and skill: each upstream file maps to the core files it became, or to DROP with a reason.
- A re-pin is a reviewed change that diffs the two pins and replays the change list.

**Distilled:** the ideas rewritten in the layer's own words, with no copied sentence or code. Credit the source by name only (with its license when it has one) in the layer root's `ATTRIBUTIONS.md`. This is the only form for a source with no open license, and a choice for any other.

## Bad Example

```markdown
## Description

Retries must be bounded and jittered.

Source: Jane Doe, "Retry Patterns", with a link to her blog. The paragraph below
is copied from chapter 3.
```

A rule that names its author, links out and pastes an upstream paragraph with no license copy and no change list.

## Good Example

A mapping row for a vendored file, in core's `ATTRIBUTIONS.md`:

```markdown
### acme-billing

| Upstream file | Core files | Changes |
| --- | --- | --- |
| `skills/money/rounding.md` | `rules/acme-decimal-amounts.md` | Retitled; examples use Decimal; References list removed. |
| `skills/money/locales.md` | DROP | Covers display formatting, which no rule here owns. |
```

A credit line for a distilled idea, in the layer root's `ATTRIBUTIONS.md`:

```markdown
The retry budget in `acme-retry-budget` distills ideas from Jane Doe's
"Retry Patterns" (no open license), credited by name only; no text is copied.
```

## Notes

- No URL anywhere, attribution included; the eval fixtures' license URI is the one listed exception.
- Outside `ATTRIBUTIONS.md` and the license copies, no file names a source the CI scan knows; distilling from a new source adds its name to that scan.
- Engine-written core files are listed per skill as not vendored.
- Adapted text still follows every engine decision: rule shape, size limits, gates and ids.
- Continue receives rules without the license copies, an accepted gap.
- Write a core license copy's name generically as LICENSE.<source-slug> in prose: the real names contain source markers the scan bans in core.
- plugin-template.md has ATTRIBUTIONS skeletons for both forms.
