"""The ``playbook-hook`` runtime: one import-light process per harness event (specs/prK-lifecycle-hooks.md §D).

It reads the harness payload, normalizes it into a ``CanonicalEvent``, fans out
in-process to the enabled hooks, combines their results under one decision rule
and renders that decision back into the harness's wire format.

This module is a docstring only and imports nothing: every harness event pays
for whatever the package root loads, within a 100 ms budget (§D.1). The hot
path imports only the standard library, ``hook_runtime.*``, ``security.*``,
``artifacts.path_classes`` and ``artifacts.path_globs``.
"""
