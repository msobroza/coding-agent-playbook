---
id: arch-one-layout-axis
name: One layout axis
description: "Organize packages along one axis, layer-first or feature-first, follow the axis the repo already uses, and make the architecture visible in the folder tree."
version: 1
scope: scoped
globs:
  - "**/__init__.py"
section: layout
priority: 61
tags: [python, architecture, layout]
---

# Organize packages along one layout axis

## Description

The folder tree is the first architectural statement a project makes. A module (`.py` file) groups related functions and classes; a package (a folder with `__init__.py`) groups related modules; a sub-package nests further once a package grows. There are two ways to arrange them:

| | Layer-first | Feature-first |
| --- | --- | --- |
| Top level | one package per layer: `routers/`, `operations/`, `db/`, `domain/` | one package per feature: `bookings/`, `billing/` |
| Strength | the architecture is visible from the top level | a feature reads, and can be deleted, as one folder |
| Cost | one feature change touches several directories | each feature repeats the same inner structure |
| Extra rule | none | features talk through each other's application layer, never through each other's `db` |

Both may nest the other axis one level down: features inside each layer, or layers inside each feature. Follow the axis the repo already uses; a new repo picks one and applies it everywhere. Mixing them leaves two places to look for every piece of code.

## Bad Example

```text
src/hotel/
  routers/bookings.py
  operations/bookings.py
  billing/
    router.py       # a feature folder beside layer folders
    operations.py
    db.py
```

## Good Example

```text
src/hotel/
  main.py
  bookings/
    __init__.py
    routers.py
    operations.py   # calls billing.operations, never billing.db
    db.py
    domain.py
  billing/
    __init__.py
    routers.py
    operations.py
    db.py
    domain.py
tests/
  bookings/test_operations.py
  billing/test_operations.py
```

## Notes

- Keep `__init__.py` small: no logic and few re-exports, because every re-export adds a second path to the same name.
- A folder without `__init__.py` still imports, as a namespace package, but tools that discover packages may skip it; give every package of your own an `__init__.py`.
- A layer name counts anywhere in a module's dotted path, so `bookings/routers.py` and `routers/bookings.py` are both interface code; singular names such as `bookings/service.py` match no layer until the skill's layer_map.py script is told about them with `--layer`.
- A scaffolded tree lists dependencies in `pyproject.toml`, not a requirements file, and keeps test fakes under `tests/`.
- How the tree reads to a newcomer is arch-predictable-project-tree; generic package names are arch-no-junk-drawer-packages.
