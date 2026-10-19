"""Shell parsing for the Bash guards (specs/prK-lifecycle-hooks.md §D.2.5).

``parse`` is the interface: ``parse_shell`` turns command text into
``Segment``s. ``tokens`` and ``_scan`` are the lexer, ``_options`` and
``wrappers`` strip the launchers, ``segments`` assembles the segments and
``writes`` lists the files a segment writes. ``wrapper_policy`` decides which
launchers a guard may look through, ``git_command`` parses a git command found
in a segment and ``git_options`` reads its global options. The handlers import
these modules directly, so this module is a docstring only.
"""
