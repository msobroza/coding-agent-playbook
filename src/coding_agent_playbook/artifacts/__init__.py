"""The guidance artifacts: Rule, Prompt, Skill and Hook, and the leaves they share (SPEC §6.6).

Deliberately empty: import the defining module (``artifacts.hook_schema`` for the
HOOK.md key sets and vocabulary, ``artifacts.hook_frontmatter`` for
``HookFrontmatter``, ``artifacts.member_reference`` for a member rule as its Skill
delivers it as a Reference). ``hook_policy`` loads the stdlib-only
``artifacts.hook_schema`` on its light path, so this package must import nothing.
"""
