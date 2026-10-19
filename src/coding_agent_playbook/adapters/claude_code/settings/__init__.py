"""The managed merge into the co-owned ``.claude/settings.json`` and its drift check.

``managed_merge`` is the interface (``merge_managed_entries``, ``write_settings``,
``parse_settings``); ``drift`` is how ``playbook check`` judges the managed elements.
``_plan``, ``_json_spans`` and ``_json_edits`` are the merge's internal seams. This
module is a docstring only: import the defining module.
"""
