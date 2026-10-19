"""The guidance artifacts: Rule, Prompt, Skill and Hook, and the leaves they share (SPEC §6.6).

Deliberately empty: import the defining module (``artifacts.rule``, ``artifacts.prompt``,
``artifacts.skill`` and ``artifacts.hook`` for the four artifacts,
``artifacts.frontmatter`` for the markdown + YAML frontmatter format they share,
``artifacts.hook_schema`` for the HOOK.md key sets and vocabulary,
``artifacts.hook_frontmatter`` for ``HookFrontmatter``, ``artifacts.member_reference``
for a member rule as its Skill delivers it as a Reference, ``artifacts.identity`` for
the id and template name an artifact is known by, ``artifacts.path_classes`` for the
eval-task and test path classes, ``artifacts.path_globs`` for the path-glob grammar and
``fold_key``). ``hooks`` loads the stdlib-only ``artifacts.hook_schema`` on its light
path, and the hook runtime and the grading kernel load the stdlib leaves
``artifacts.path_classes`` and ``artifacts.path_globs``, so this package must import
nothing.
"""
