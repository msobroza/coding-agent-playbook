"""Per-subcommand modules for the ``playbook`` CLI.

Each subcommand is one public module, here or in ``twins/``: it defines ``NAME``,
``HELP``, ``configure(parser)`` (its flags) and ``run(args) -> int``, the Command
protocol of ``cli/_command.py``, and imports nothing from ``cli``. The ``cli``
package's parser (``cli/parser.py``) imports each module, lets it declare its flags
and binds its ``run`` as the subparser's ``func``.
Splitting per-command keeps each command's flags, logic and tests together.
"""
