"""Reading ``guard_config.json``, the hook runtime's only configuration (specs/prK-lifecycle-hooks.md §D.8).

``guard_config`` loads and trusts the file, ``schema`` holds the contract names
sync's writer shares with it, ``guard_tables`` reads its pack tables through
typed accessors, ``reader`` bounds its reads and types its
values, ``keys`` declares the handler config keys, ``hook_records`` parses the
per-hook records, ``lock_digest`` reads the trusted digest from the lockfile,
``pin`` holds the interpreter and tool pins, and ``protected`` the set of paths
sync owns. The dispatcher loads ``guard_config`` on every event, so this module
is a docstring only.
"""
