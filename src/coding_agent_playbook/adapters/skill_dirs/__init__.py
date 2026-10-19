"""The skill-directory writer the harness adapters share, and its prior-output ownership read.

``writer`` writes each skill as a native ``<root>/<id>/`` directory (``SKILL.md``,
byte-copied ``scripts/``/``references/`` and member-rule references) for the adapters
that ship skills natively; ``ownership`` tells it which skill directories a previous
sync wrote, through the context sync installs. This module is a docstring only:
import the defining module.
"""
