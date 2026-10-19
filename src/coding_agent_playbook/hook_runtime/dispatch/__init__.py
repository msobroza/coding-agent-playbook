"""The hook dispatcher and the model it decides with (specs/prK-lifecycle-hooks.md §D.1-§D.9).

``run`` is the dispatch pipeline every hook process runs: one harness event in,
one decided output out. Its private steps are ``_pipeline`` (steps 3-9),
``_execute`` (the handlers under the failure policy), ``_faults`` (what the
dispatcher decides when it cannot run the hooks), ``_post_write`` and
``_decision_log`` (what a dispatch records after its write).

``event`` holds the ``CanonicalEvent`` every harness payload is normalized
into, ``paths`` the git-free repo discovery and the ``NormalizedPath`` its
fields carry, ``decision`` the ``HandlerResult`` and ``Decision`` model
handlers return, ``caps`` the output caps and sanitization, and ``policy`` the
attendance and failure-policy tables.

``registry`` binds hook ids to builtin and entry-point handlers
(``register_hook_handler``, ``HandlerContext``); ``selection``, ``routing``
and ``prefilter`` decide which hooks run on an event and where; ``external``
runs a repo or overlay script behind a trust approval; ``combine`` folds the
results into one decision; ``tail`` and ``watchdog`` end every dispatch with
the one output write; ``escape`` reads the kill switches and escape hatches.
``deps`` (``RuntimeDeps``), ``ports`` (git and the trust store), ``proc`` (the
one process seam) and ``event_memo`` (work shared by an event's hooks) are the
injected effects. Importers name these modules directly, so this module is a
docstring only.
"""
