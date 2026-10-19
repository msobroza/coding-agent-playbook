"""Sync: one ``playbook sync`` run, which resolves the catalog, renders every adapter's Generated output and writes the Lockfile.

Deliberately empty: import the defining module. ``pipeline`` is the run itself
(``execute``, which ``playbook sync`` and ``playbook init`` call), ``render`` the
render step ``playbook render`` shares, and ``git_client`` the read-only git
interface tests replace with a fake. The underscore modules are its steps:
``_check_modes`` (``--check`` and ``--check-staged``), ``_dispatch`` (the adapter
dispatch and the lockfile stamp), ``_hook_outputs`` and ``_machine_local`` (the
hook outputs and the machine-local hook pins), ``_leftovers`` (what an earlier sync
left behind), ``_output_policy`` (the ``[output] commit`` policy) and
``_output_blockers`` (what stands in the way of a write).
"""
