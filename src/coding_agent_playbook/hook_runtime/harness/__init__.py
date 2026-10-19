"""Harness I/O: payload parsers and wire renderers (specs/prK-lifecycle-hooks.md §D.2.2, §D.3.5).

Each harness module has one parser and one renderer. A parser turns the
stdin bytes into a ``CanonicalEvent``, a ``ForeignPayload`` (another harness
reached us through ``.claude/settings.json``: stay inert, §C.5.2) or a
``ContractFault`` (our own harness sent something unusable: the failure
policy decides, §D.4). A renderer turns a ``CombinedResult`` into the
``WireOutput`` the dispatcher writes once; it never touches a stream itself.

The dispatch process exits ``0`` or ``DENY_EXIT``. It never exits 2 itself:
the launcher and the OpenCode shim map 10 to the harness deny, so a crash or
a usage error that happens to exit 2 can never pass for a deny (K-7).
"""
