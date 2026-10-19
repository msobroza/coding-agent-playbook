"""The skill-directory writer the harness adapters share, and its prior-output ownership read.

``writer`` emits rendered rules as native skill directories (``SKILL.md`` plus copied
files) for the adapters that deliver rules as skills; ``ownership`` tells it which
skill directories a previous sync wrote, through the context sync installs. This
module is a docstring only: import the defining module.
"""
