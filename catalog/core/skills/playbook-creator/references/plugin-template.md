# Plugin and overlay template

A bundled plugin is pure content inside the engine repository; an overlay is an importable package an organization publishes. Both hold the same kind directories as any layer (`playbook-layer-placement`). Copy the skeleton you need, replace the placeholders and run `playbook validate`. Layout: `playbook-plugin-layout`; credit: `playbook-third-party-content`.

## Contents

- Bundled plugin tree
- README skeleton
- Overlay package tree
- Framework metadata
- ATTRIBUTIONS for vendored text
- ATTRIBUTIONS for distilled ideas
- Checklist

## Bundled plugin tree

```text
catalog/plugins/<name>/        # <name> is a Python identifier: acme_tools
├── README.md
├── LICENSE                    # only when it vendors text
├── ATTRIBUTIONS.md            # only when it uses a third-party source
├── framework.toml             # only when it is a framework
└── rules/                     # only the kind directories it needs
    └── acme-tools-tracker.md
```

## README skeleton

```markdown
# acme_tools (bundled plugin)

<What it is, in two sentences, and where its content comes from.>

## Enable it

<The overlays_enabled line, above the first table, then playbook sync.>

## Once per repo

<Any setup, and how many skill descriptions it adds to the listing.>
```

No links: files at a layer root ship but never sync.

## Overlay package tree

```text
acme-playbook/
├── pyproject.toml
└── src/acme_playbook/
    ├── __init__.py
    └── resources/
        ├── rules/
        ├── skills/
        └── hooks/
```

```toml
[project]
name = "acme-playbook"
version = "0.1.0"
dependencies = ["coding-agent-playbook>=0.21,<1"]

[build-system]
# <your build backend, configured to ship src/acme_playbook/resources/ as package data>
```

A consumer enables it by import name, with the top-level `overlays_enabled = ["acme_playbook"]` above the first `[table]` of its config. A pre-commit hook that runs playbook in its own environment lists the overlay in `additional_dependencies`, or uses `repo: local` with `language: system`.

## Framework metadata

`framework.toml` at a plugin's root or an overlay's `resources/` root marks a spec-driven framework:

```toml
name = "acme"                  # the short name for --framework
description = "Plan, test first and review the Acme way."

[layout_aliases]               # optional: a path prefix the text uses -> a layout key
"docs/acme/plans/" = "plans"
```

A repo picks at most one framework, with `playbook init --framework <name>` or the committed `framework` key. The skills write document paths in the default form that `docs-document-layout` in python-documentation lists; sync rewrites them to the repo's `[layout]` table. Each framework skill declares the roles it fills in its own frontmatter, such as `capabilities: [clarify]`.

## ATTRIBUTIONS for vendored text

```markdown
## <source name>

Source: <source name>, version <tag>, commit `<pin>`.
Author: <author>. License: <license>; the copy ships as LICENSE.

| Upstream file | Files here | Changes |
| --- | --- | --- |
| `<upstream path>` | `rules/<id>.md` | <Every change: retitled, examples rewritten, lists removed.> |
| `<upstream path>` | DROP | <Why nothing here uses it.> |

Re-pin: diff the two commits, replay the change list, review it as one change.
```

## ATTRIBUTIONS for distilled ideas

```markdown
## <source name>

Distilled (credited by name only, not vendored): <source name> by <author>
(<license, or no open license>). `rules/<id>.md` restates <the idea> in our
own words; no sentence or example is copied.
```

## Checklist

- The plugin name is an identifier; the plugin holds no Python module; only kind directories ship content.
- Vendored text ships its license byte-identical, with a change list per file.
- A framework declares `name` and `description`, and at most one framework is on.
- The README says how to enable it; no file links out, and no URL appears, attribution included.
