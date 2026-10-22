---
id: playbook-plugin-layout
name: Plugin and overlay layout
description: "Ship a bundled plugin as pure content and an overlay as an importable package, each with the layer's kind directories."
version: 1
scope: scoped
globs:
  - "catalog/plugins/*/*"
  - "src/*/resources/**"
  - "src/*/__init__.py"
applies_if:
  playbook_layer: true
section: plugins
priority: 60
tags: [playbook, plugins]
---

# Lay out a bundled plugin as content and an overlay as a package

## Description

**A bundled plugin** is pure content at `catalog/plugins/<name>/`, off by default:

- `<name>` is a Python identifier not starting with `_` or `.` (`acme_tools`, not `acme-tools`).
- It holds at least one kind directory, a `README.md` saying what it is and how to enable it (the `overlays_enabled` line, or `--framework` for a framework), `ATTRIBUTIONS.md` for any third-party source and `LICENSE` for vendored text, and no Python module.
- Its skills normally carry no `playbook:` block (a vendored skill keeps its own "Use when"). It adds to core guidance through always rules, or through rules joining a core skill with `skill:` and `section:`.

**An overlay** is an importable Python package whose `resources/` directory holds the same kind layout. A consumer lists its import name in `overlays_enabled`, a top-level key above the first `[table]`. The package ships `resources/` as package data and depends on a compatible coding-agent-playbook range. A pre-commit hook running playbook in its own environment needs the overlay in `additional_dependencies`, or uses `repo: local` with `language: system`.

**A framework** (a plugin or overlay supplying the spec-driven workflow) declares itself in `framework.toml` at a plugin's root or an overlay's `resources/` root: `name` (the short name for `--framework`), `description` and an optional `[layout_aliases]` table. Consumers pick at most one with `playbook init --framework <name>` (superpowers, mattpocock, none, or an overlay's full module name) or the committed `framework` key. Its skills write document paths in the document layout's default form (`docs-document-layout` in python-documentation lists it); sync rewrites those prefixes for a repo whose `[layout]` differs. A framework whose text uses other paths maps them in `[layout_aliases]` (path prefix to layout key) instead of templating its text. Each framework skill declares the roles it fills in its own frontmatter, such as `capabilities: [clarify]` (roles: clarify, clarify_with_docs, spec, plan, tdd, debug, review, verify; one skill per role per framework); the engine strips the key from written files, and `playbook check` prints the role map.

## Bad Example

```text
catalog/plugins/acme-skills/
├── __init__.py          # a plugin is never imported
├── README.md            # holds a link to the team wiki
└── notes.md             # no kind directory at all
```

The name is not an identifier, the module and the link break the content gates, and nothing here is a kind directory.

## Good Example

```text
catalog/plugins/acme_tools/        src/acme_playbook/
├── README.md                      ├── __init__.py
├── ATTRIBUTIONS.md                └── resources/
└── rules/                             ├── framework.toml
    └── acme-tools-tracker.md          ├── skills/
                                       └── hooks/
```

```toml
# src/acme_playbook/resources/framework.toml
name = "acme"
description = "Plan, test first and review the Acme way."

[layout_aliases]
"docs/acme/plans/" = "plans"
```

```toml
# the consumer's .coding-agent-playbook.toml, above the first [table]
overlays_enabled = ["coding_agent_playbook.plugins.acme_tools"]
framework = "acme_playbook"
```

## Notes

- Every enabled plugin's skill descriptions count toward the listing budget (core plus each plugin).
- Try a plugin with a non-interactive init in an empty scratch directory, with stdin from /dev/null.
- In the engine, CI gates every plugin directory with no test edit: the URL and source-name scan, the link gate and the layout guards.
- The layout guard hook blocks spec and plan writes outside the configured directories.
- plugin-template.md has both skeletons.
