"""The secret-path catalog: one list of credential-file globs (SPEC §17.3).

This is the **only** home of these constants (specs/prK-lifecycle-hooks.md §P7).
The detector skips every match, and later consumers (the ``sync --check`` scratch
copy, the path guards via ``guard_config.json``) read the same tuples, so no two
parts of the engine can disagree about what a secret path is. Overlays and
consumers may only *extend* the globs, never shrink them.

The module performs **zero runtime imports**: the hook dispatcher loads it on its
hot path (§D.1).

Glob grammar, as matched by :func:`coding_agent_playbook.security.paths.is_secret_path`
(``fnmatch`` syntax, case-folded on darwin/win32):

- a glob without ``/`` matches a path's final component in any directory, so
  ``*.pem`` matches ``certs/server.pem``;
- a glob starting with ``~/`` is anchored at the user's home directory, and a
  trailing ``/**`` matches everything below that directory.

A path is secret when it matches a :data:`SECRET_PATH_GLOBS` entry that is not
cancelled for it: :data:`SECRET_PATH_EXEMPT` cancels every glob, while a
:data:`SECRET_GLOB_EXEMPT` exemption cancels only its own glob (so the
source-code exemption of ``*credentials*`` never spares ``.env.credentials.py``
or ``id_rsa_credentials.sh``). Exemptions are final-component globs.
"""

# A local constant instead of ``typing.TYPE_CHECKING`` keeps the module free of
# runtime imports; mypy treats any name ``TYPE_CHECKING`` as true.
TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Final

SECRET_PATH_GLOBS: "Final[tuple[str, ...]]" = (
    # SPEC §17.3's original four; *credentials* spares source code via the exemptions.
    ".env*",
    "*.pem",
    "*.key",
    "*credentials*",
    # key stores and SSH private keys (public keys are exempt)
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    "id_rsa*",
    "id_ed25519*",
    "id_ecdsa*",
    "id_dsa*",
    # package-manager, VCS and secret-store credential files
    ".netrc",
    ".pypirc",
    ".npmrc",
    "pip.conf",
    "uv.toml",
    ".git-credentials",
    ".vault-token",
    "krb5cc_*",
    # infrastructure state/variables and password vaults
    "*.tfstate",
    "*.tfstate.*",
    "*.tfvars",
    "*.tfvars.json",
    "*.kdbx",
    # per-user credential stores
    "~/.aws/**",
    "~/.ssh/**",
    "~/.kube/config",
    "~/.config/gcloud/**",
    "~/.config/gh/hosts.yml",
    "~/.docker/config.json",
    "~/.m2/settings.xml",
    "~/.claude/.credentials.json",
)

#: Source-code suffixes for which ``*credentials*`` does not fire: a module that
#: *handles* credentials (``credentials.py``) is code, not a credential store.
#: Notebooks are deliberately absent because they persist cell outputs, and
#: data/config formats (json, yaml, toml, ini, xml, ...) stay secret.
_CREDENTIALS_CODE_SUFFIXES: "Final[tuple[str, ...]]" = (
    "py",
    "pyi",
    "pyx",
    "js",
    "jsx",
    "mjs",
    "cjs",
    "ts",
    "tsx",
    "go",
    "rs",
    "java",
    "kt",
    "scala",
    "rb",
    "php",
    "cs",
    "c",
    "h",
    "cpp",
    "hpp",
    "swift",
    "sh",
    "bash",
    "ps1",
    "sql",
    "tf",
)

SECRET_PATH_EXEMPT: "Final[tuple[str, ...]]" = (
    # documented .env templates carry variable names, not values
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.dist",
    # public halves of SSH key pairs
    "id_rsa*.pub",
    "id_ed25519*.pub",
    "id_ecdsa*.pub",
    "id_dsa*.pub",
)

#: Exemptions scoped to one glob (glob -> the globs that cancel it, and only
#: it): ``*credentials*`` spares source code, yet a path that also matches
#: another glob (``.env.credentials.py``) stays secret. Never mutated.
SECRET_GLOB_EXEMPT: "Final[dict[str, tuple[str, ...]]]" = {
    "*credentials*": tuple(f"*credentials*.{suffix}" for suffix in _CREDENTIALS_CODE_SUFFIXES),
}
