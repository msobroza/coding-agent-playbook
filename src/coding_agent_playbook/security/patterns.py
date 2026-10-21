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
  trailing ``/**`` matches everything below that directory;
- any other glob with a ``/`` is anchored at the start of the path: the
  repository root for a relative glob (``.git/**/glab-cli/config.yml``), the
  filesystem root for one starting with ``/``. ``**`` spans directories.

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
    # glab's config, which holds its token when no keyring is used: ~/.config/glab-cli
    # (Linux, and the legacy path glab reads first on every OS), then the macOS and
    # Windows defaults; the aliases.yml beside it holds no credentials. Then the
    # repository config, ``$(git rev-parse --git-dir)/glab-cli/config.yml``, in the main
    # checkout's, a linked worktree's or a submodule's git dir.
    "~/.config/glab-cli/config.yml",
    "~/Library/Application Support/glab-cli/config.yml",
    "~/AppData/Local/glab-cli/config.yml",
    ".git/**/glab-cli/config.yml",
    # the GitLab Runner config with its runner authentication token: a non-root
    # runner's, then a root one's (on Windows it has no fixed path: the working directory)
    "~/.gitlab-runner/config.toml",
    "/etc/gitlab-runner/config.toml",
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

# --- secret *content* (specs/prK-hook-pack.md §E.4) -------------------------------------
#
# Each rule is ``(rule id, regex source, label)``: sources, not compiled patterns,
# because this module imports nothing (``security.secrets`` compiles them once).
# Only high-precision vendor formats with a fixed prefix; a generic entropy rule
# is deliberately absent. Every source STARTS with its literal prefix and puts
# the left boundary in a look-behind just after it: a leading look-behind
# defeats ``re``'s literal-prefix search and made a 1.6 MB scan 50x slower
# (40 ms against 0.7 ms per rule, measured on CPython 3.13). All rules together
# scan 512 KiB of source in about 3 ms.

#: The engine ruleset's identity in ``guard_config.secret_rules``: bump the version
#: whenever a rule is added, removed or changed, so a synced config names the
#: ruleset its guards were reviewed against.
SECRET_RULESET_ID: "Final[str]" = "engine-secrets"
SECRET_RULESET_VERSION: "Final[int]" = 2

SECRET_CONTENT_RULES: "Final[tuple[tuple[str, str, str], ...]]" = (
    (
        "private-key",
        r"-----BEGIN[ A-Z0-9]{0,40}PRIVATE KEY(?: BLOCK)?-----",
        "PEM private key",
    ),
    (
        "aws-access-key-id",
        r"(?:AKIA|ASIA)(?<![A-Za-z0-9_].{4})[A-Z0-9]{16}(?![A-Za-z0-9_])",
        "AWS access key id",
    ),
    (
        "github-token",
        r"gh(?<![A-Za-z0-9_]gh)(?:[pousr]_[A-Za-z0-9]{36,255}|ithub_pat_[A-Za-z0-9_]{22,255})"
        r"(?![A-Za-z0-9_])",
        "GitHub token",
    ),
    (
        # GitLab's documented prefixes (docs "Token overview"), each at the lengths its
        # generator makes: a routable body (27-300 base64url, ``.``, an optional version
        # and ``.``, 9 base36) for pat/rt/rtr/agent/wt; a 20-char friendly token; the
        # 17.5-17.10 partitioned runner token; 50-char agent, 40-hex trigger and 64-hex
        # OAuth secret tokens; the feed token's path-dependent form; the unpadded base36
        # incoming-mail token; the job token's ``<partition>_<20>`` and JWT forms. An
        # instance prefix (``acme-glpat-...``) matches; an admin's custom PAT prefix needs
        # an ``extra_patterns`` row.
        "gitlab-token",
        r"gl(?<![A-Za-z0-9_]gl)(?:"
        r"(?:pat|rtr?|agent|wt)-[0-9A-Za-z_-]{27,300}\.(?:[0-9a-z]{2}\.)?[0-9a-z]{9}"
        r"|(?:pat|dt|rtr?|ptt|ft|soat|ffct)-[0-9A-Za-z_-]{20}|rt-t[1-3]_[0-9A-Za-z_-]{20}"
        r"|agent-[0-9A-Za-z_-]{50}|ptt-[0-9a-f]{40}|oas-[0-9a-f]{64}|ft-[0-9a-f]{64}-[0-9]+"
        r"|imt-[0-9a-z]{21,25}|cbt-(?:[0-9A-Za-z]{1,5}_[0-9A-Za-z_-]{20}"
        r"|eyJ[0-9A-Za-z_-]{8,}\.eyJ[0-9A-Za-z_-]{8,}\.[0-9A-Za-z_-]{8,})"
        r")(?![0-9A-Za-z_-])",
        "GitLab token",
    ),
    (
        # Project and group runner registration tokens; the instance-wide one has no prefix.
        "gitlab-runner-registration-token",
        r"GR1348941(?<![A-Za-z0-9_].{9})[0-9A-Za-z_-]{20}(?![0-9A-Za-z_-])",
        "GitLab runner registration token",
    ),
    ("slack-token", r"xox[abprs]-(?<![A-Za-z0-9_].{5})[A-Za-z0-9-]{10,250}", "Slack token"),
    (
        "google-api-key",
        r"AIza(?<![A-Za-z0-9_-].{4})[0-9A-Za-z_-]{35}(?![0-9A-Za-z_-])",
        "Google API key",
    ),
    # ``sk_live_`` only: a ``(?:sk|rk)`` alternation has no literal prefix and
    # scanned 20x slower than every other rule (``s`` and ``r`` are everywhere).
    ("stripe-live-key", r"sk_live_(?<![A-Za-z0-9_].{8})[0-9A-Za-z]{16,247}", "Stripe live key"),
    (
        "anthropic-api-key",
        r"sk-ant-(?<![A-Za-z0-9_].{7})[A-Za-z0-9_-]{20,250}",
        "Anthropic API key",
    ),
    (
        "openai-api-key",
        r"sk-proj-(?<![A-Za-z0-9_].{8})[A-Za-z0-9_-]{20,250}",
        "OpenAI project API key",
    ),
    (
        "azure-storage-key",
        r"AccountKey=[A-Za-z0-9+/]{40,120}={0,2}",
        "Azure storage account key",
    ),
    (
        "jwt",
        r"eyJ(?<![A-Za-z0-9_-].{3})[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
        "JSON Web Token",
    ),
    (
        # ``scheme://user:password@host``; placeholders (``${PW}``, ``<pw>``,
        # ``%(pw)s``, ``***``, ``password``) are documentation, not secrets.
        "url-credentials",
        r"://[^\s:/@'\"<>]{1,128}:(?!(?:password|passwd|pass|pwd|secret|x+|\*+)@)"
        r"[^\s/@'\"<>$%{}*]{3,128}@[A-Za-z0-9.-]{1,253}",
        "URL with inline credentials",
    ),
)

#: Published documentation examples (AWS's docs keys, jwt.io's sample token):
#: a match equal to one of these is not a finding.
EXAMPLE_SECRET_ALLOWLIST: "Final[frozenset[str]]" = frozenset(
    {
        "AKIAIOSFODNN7EXAMPLE",
        "AKIAI44QH8DHBEXAMPLE",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9l"
        "IiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    }
)

#: Lockfiles (by final component) never scanned for secret content: they hold
#: integrity hashes and resolved URLs, never hand-written credentials.
SECRET_SCAN_SKIP_NAMES: "Final[frozenset[str]]" = frozenset(
    {
        "uv.lock",
        "poetry.lock",
        "pdm.lock",
        "Pipfile.lock",
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "bun.lock",
        "Cargo.lock",
        "Gemfile.lock",
        "composer.lock",
        "go.sum",
        "flake.lock",
    }
)

#: Directories a repository walk never enters: the detector's and the secret
#: guards' (the secrets-path-guard inode index). Virtualenvs hold uv's hard
#: links, which must not read as copies of a credential file.
WALK_SKIP_DIRS: "Final[frozenset[str]]" = frozenset(
    {".venv", "venv", "node_modules", ".git", "__pycache__", ".tox", ".mypy_cache"}
)

#: ``# playbook: allow-secret <rule-id>[, <rule-id>...]`` waives the named rules on its
#: line, and only when that line is already committed at the base revision. The
#: ``rules`` group runs to the next ``#``; ``security.secrets`` splits the ids.
ALLOW_SECRET_PRAGMA: "Final[str]" = r"playbook:\s*allow-secret\b(?P<rules>[^#\n]*)"

#: destructive-command-guard's literal-prefix shapes (specs/prK-hook-pack.md §E.4), each
#: catastrophic whatever follows it. While the guard is on, the claude_code adapter also
#: renders them as native ``permissions.deny`` ``Bash(<prefix> *)`` rows, which still hold
#: when the hook interpreter is missing; the guard's predicate rows (realpath'd targets,
#: dirty-tree checks, protected-branch globs) have no native form. No prefix may hold a
#: ``*``: Claude reads one as a wildcard anywhere in the rule (``rm -rf /*`` would deny
#: every ``rm -rf /tmp/...``).
DESTRUCTIVE_NATIVE_PREFIXES: "Final[tuple[str, ...]]" = (
    "rm -rf /",
    "rm -fr /",
    "rm -rf ~",
    "rm -fr ~",
    "rm -rf $HOME",
    "mkfs",
    "git push --force origin main",
    "git push -f origin main",
    "git push --force origin master",
    "git push -f origin master",
    "git push --mirror",
    "chmod -R 777 /",
)
