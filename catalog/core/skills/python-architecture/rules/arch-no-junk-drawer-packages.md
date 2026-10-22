---
id: arch-no-junk-drawer-packages
name: No junk-drawer packages
description: "Never name a package or module utils, helpers, common, misc or managers: place each function in the package of the concept it serves."
version: 1
scope: scoped
globs:
  - "**/utils/**/*.py"
  - "**/utils.py"
  - "**/helpers/**/*.py"
  - "**/helpers.py"
  - "**/common/**/*.py"
  - "**/common.py"
  - "**/managers/**/*.py"
  - "**/misc.py"
  - "**/__init__.py"
section: layout
priority: 62
tags: [python, architecture, layout]
---

# Name packages for what they hold, never utils

## Description

A package named `utils`, `helpers`, `common`, `misc` or `managers` says that nobody decided where its contents belong. It becomes a junk drawer: unrelated functions accumulate, every other package imports it, and a change to one helper risks all of its importers. Find out what each function does and move it into the package of the concept it serves.

Interface modules that hold request or event handlers are fine: there, "handler" names a role in the architecture, not a leftover.

## Bad Example

```text
src/hotel/
  utils/
    helpers.py   # helpers for what?
    misc.py      # miscellaneous what?
    common.py    # common to what?
  managers/
    data_manager.py
    user_manager.py
```

## Good Example

```text
src/hotel/
  guests/
    validation.py    # was utils/validate_guest.py
    formatting.py    # was utils/format_address.py
  pricing/
    discounts.py     # was utils/calculate_discount.py
```

## Notes

- A function without a home is a design signal: it belongs in an existing package, or it reveals a missing domain concept that deserves its own.
- A module that nearly every other module imports, and that mixes concerns, is a hub: split it along the concepts it serves.
- A small package-private helper module next to its only caller (`bookings/_dates.py`) is fine; the problem is a shared drawer with no subject.
- The tree as a whole is arch-predictable-project-tree; the layout axis is arch-one-layout-axis.
