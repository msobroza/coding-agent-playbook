---
id: arch-predictable-project-tree
name: Predictable project tree
description: "Keep the project tree predictable: one root package, tests mirroring it, the framework's conventional directories, and no ad-hoc top-level folders or flat dumps."
version: 1
scope: scoped
globs:
  - "**/*.py"
  - "pyproject.toml"
section: layout
priority: 60
tags: [python, architecture, layout]
---

# Keep the project tree predictable

## Description

A good tree lets one path predict its neighbors. If `app/routers/bookings.py` exists, a reader can expect `app/operations/bookings.py` and `tests/routers/test_bookings.py` without listing a directory. When files are named ad hoc or piled into one folder, every lookup turns into a search or a directory listing. That slows down a new teammate, and it costs a coding agent time and tokens on every task: in a repo with no conventions it has to infer one by exploring, and it pays for that exploration again until it has.

- Keep the repo's existing root package. A new project puts its code in one package under `src/<package>/`, never as loose modules beside `pyproject.toml`.
- Mirror the package tree in `tests/`, so each module's tests sit at the matching path.
- Keep the conventional directories of the framework the repo uses, such as a web app's routers, schemas and operations modules, instead of inventing new names for the same roles.
- Put engineering documents where the document layout says (the glossary, decision records, specs and plans), not in new top-level folders.
- Add no ad-hoc top-level folder (`new/`, `stuff/`, `v2/`, `scripts2/`) and no flat dump of unrelated modules.

## Bad Example

```text
project/
  pyproject.toml
  main.py
  helpers2.py
  booking_stuff.py
  new_booking_logic.py
  db_things.py
  test_everything.py
  notes/
    design-ideas.md
```

## Good Example

```text
project/
  pyproject.toml
  src/hotel/
    __init__.py
    main.py
    routers/bookings.py
    operations/bookings.py
    db/bookings.py
    domain/bookings.py
  tests/
    routers/test_bookings.py
    operations/test_bookings.py
    db/test_bookings.py
  docs/adr/0001-booking-overlaps.md
```

## Notes

- The axis inside the package (layer-first or feature-first) is arch-one-layout-axis; generic package names such as utils and helpers are arch-no-junk-drawer-packages.
- Where specs, plans and decision records go is the python-documentation skill's docs-document-layout rule.
