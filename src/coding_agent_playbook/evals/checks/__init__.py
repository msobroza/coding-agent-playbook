"""The eval-only check families: the file, answer and across-trial aggregate checks.

Deliberately empty: import the defining module. ``files`` gates on the candidate
tree, ``answer`` on the graded artifact and ``aggregate`` on the trials of a run;
each registers its checks with ``@register_check`` when the handle builder
(``evals.compile._handles``) imports it.
"""
