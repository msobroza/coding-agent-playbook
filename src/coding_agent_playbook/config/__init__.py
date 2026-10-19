"""The consumer config: the committed config file and its machine-local overrides (SPEC §7).

Deliberately empty: import the defining module (``config.model`` for ``Config``,
``config.schema`` for ``ConfigError``, ``config.files`` for ``FileSystemStateSource``,
``config.tables.hooks`` for the hook policy tables). The hook policy imports
``config.tables.hooks`` on a light path, so loading it must not load the others.
"""
