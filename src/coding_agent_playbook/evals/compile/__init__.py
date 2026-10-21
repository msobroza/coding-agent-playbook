"""The eval sample compiler: a sample's ``[gate]``, ``[rubric]`` and ``[aggregate]`` blocks to grading-kernel checks.

Deliberately empty: import the defining module. ``compiler`` is public (``evals.sample``
and ``evals.run.scoring`` import it); ``_expr`` and ``_handles`` serve the compiler,
and ``gate_registry`` and ``rubric_registry`` hold the named gates and rubrics a
``{ref = "name"}`` binding resolves.
"""
