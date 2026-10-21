"""Each forge and its forge CLI's grammar, as plain data (specs/prF-forge-adapter.md §4, §8).

Forges are a fixed in-tree list (Q3): :data:`GITHUB` and :data:`GITLAB`, in
:data:`FORGES` order; a third forge is one more entry. A :class:`Forge` names
its public host, its forge CLI's argv0, the env vars that name its host or
hold its token, the git push options it reads, and the forge CLI commands the
guards judge (:class:`CliCommand`): their value-taking flags, the flags and
operands that carry a local file to the forge, the flags that push ``HEAD``'s
branch, add a git remote or hold a credential. Every table is a tuple or a
frozenset of flag names: the hook runtime builds its own ``value_options()`` /
``CliWords`` from them and ``playbook forge`` reads the same forge, so the
guards and the command never disagree about a forge CLI.

Only commands a guard reads have a row. A row whose path is a single noun
(``issue``) covers that noun's other verbs, so a verb a newer CLI adds still
has its body-file flags read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "FORGES",
    "GITHUB",
    "GITLAB",
    "CliCommand",
    "CommandPath",
    "Forge",
    "PushOptionEffect",
    "by_cli",
    "by_name",
]

#: A forge CLI command's leading words, after argv0: ``("mr", "create")``.
type CommandPath = tuple[str, ...]
#: What a git push option does on the forge that reads it (spec §8.4).
type PushOptionEffect = Literal[
    "skips_secret_detection",
    "bypasses_security_policy",
    "sets_ci_input",
    "skips_ci",
    "opens_pull_request",
    "sends_text",
]

_NONE: Final[frozenset[str]] = frozenset()


@dataclass(frozen=True, slots=True)
class CliCommand:
    """One forge CLI command a guard judges: which of its words carry what (spec §8.2, §8.3).

    A flag in ``files``, ``field_files``, ``keyed_files``, ``templates`` or
    ``secrets`` takes a value; :attr:`values` is every value-taking flag. A
    value of ``-`` (or ``@-``) is stdin, not a file. ``pushes``, ``remotes``
    and ``creates_repository`` describe the command's effect, not its words.

    Example::

        >>> GITLAB.command(["snippet", "new", "notes.md"]).file_operands
        0
    """

    #: The command's words after argv0; aliases after the first.
    paths: tuple[CommandPath, ...]
    #: Value-taking flags whose value is no local file.
    options: frozenset[str] = _NONE
    #: Flags whose value is a local file the command sends to the forge.
    files: frozenset[str] = _NONE
    #: Flags whose ``key=@file`` value sends that file (``gh api -F body=@notes.md``).
    field_files: frozenset[str] = _NONE
    #: Flags whose ``key:file`` value sends that file (``glab ci run --variables-file``).
    keyed_files: frozenset[str] = _NONE
    #: Flags whose value is a sent file when it is absolute or holds a path separator,
    #: else the name of a template on the forge (Q56).
    templates: frozenset[str] = _NONE
    #: Flags whose value is a credential, redacted wherever a command line is recorded.
    secrets: frozenset[str] = _NONE
    #: The operands from this index on are local files sent to the forge; ``None``: none are.
    file_operands: int | None = None
    #: The command publishes its file operands as a gist or a snippet.
    snippet: bool = False
    #: Flags that make the command push ``HEAD``'s branch, each unless given ``=false``:
    #: ``glab mr create --fill --push=false`` still pushes (spec §8.3, Q13).
    pushes: frozenset[str] = _NONE
    #: Flags whose presence makes the command add or repoint a git remote.
    remotes: frozenset[str] = _NONE
    #: The command adds a git remote whatever its flags (``glab repo create``).
    adds_remote: bool = False
    #: The command creates a repository on the forge.
    creates_repository: bool = False
    #: The command opens a pull request (``push_requires_green`` asks first).
    opens_pull_request: bool = False

    @property
    def values(self) -> frozenset[str]:
        """Every value-taking flag of the command, the file-carrying ones included."""
        return (
            self.options
            | self.files
            | self.field_files
            | self.keyed_files
            | self.templates
            | self.secrets
        )


@dataclass(frozen=True, slots=True)
class Forge:
    """One forge, and what its forge CLI looks like to the guards and ``playbook forge``.

    Example: ``GITLAB.cli == "glab"``, ``GITLAB.host == "gitlab.com"``.
    """

    #: The ``[forge] hosts`` value and ``playbook forge which``'s ``forge``; a host
    #: name holding it maps to this forge (§5.2 rule 3).
    name: str
    #: The public instance's host (§5.2 rule 2).
    host: str
    #: The forge CLI's argv0.
    cli: str
    #: The env vars naming the forge CLI's host, in the CLI's precedence order (§5.2 rule 4).
    host_env: tuple[str, ...]
    #: The env vars naming the API host when it differs from the host (§5.3, §8.2).
    api_host_env: tuple[str, ...]
    #: The env vars the forge CLI reads a token from, in its precedence order.
    token_env: tuple[str, ...]
    #: Flags naming the repository as ``[HOST/]OWNER/REPO`` or a URL, on most commands.
    repo_flags: frozenset[str]
    #: Flags naming the forge's host outright (``api``, ``auth``).
    hostname_flags: frozenset[str]
    #: The forge CLI commands the guards judge.
    commands: tuple[CliCommand, ...]
    #: The env vars naming the repository as ``[HOST/]OWNER/REPO``, like a ``repo_flags`` value.
    repo_env: tuple[str, ...] = ()
    #: How many ``/``-separated parts a ``repo_flags`` value has when it leads with a host
    #: (``HOST/OWNER/REPO``: 3); ``None`` when a host cannot be told from a group by count
    #: (GitLab's ``GROUP/NAMESPACE/REPO``): a reader then takes a first part for a host when
    #: it is this forge's host, one its host env vars name, or a dotted name.
    repo_host_parts: int | None = None
    #: What the forge calls a published file snippet (``gist`` on GitHub).
    snippet_name: Literal["gist", "snippet"] = "snippet"
    #: The host a snippet lands on when the command names none (GitHub's gist host);
    #: empty: the repository's own host.
    snippet_host: str = ""
    #: The git push options the forge reads, by name (``ci.variable=K=V`` is ``ci.variable``).
    push_options: tuple[tuple[str, PushOptionEffect], ...] = ()
    #: ``(alias, namespace)``: a push option namespace the forge also reads under another
    #: name (GitLab's ``mr.create`` is ``merge_request.create``).
    push_option_aliases: tuple[tuple[str, str], ...] = ()
    #: Commit-message markers that make the forge skip its secret push protection.
    secret_skip_markers: tuple[str, ...] = ()
    #: Title markers that make the forge skip CI: ``playbook forge`` refuses such a
    #: pull request title (Q55). Compared case-insensitively.
    skip_ci_markers: tuple[str, ...] = ()
    _paths: tuple[tuple[CommandPath, CliCommand], ...] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        rows = [(path, row) for row in self.commands for path in row.paths]
        rows.sort(key=lambda item: -len(item[0]))
        object.__setattr__(self, "_paths", tuple(rows))

    def command(self, words: Sequence[str]) -> CliCommand | None:
        """The row of the command ``words`` (argv after argv0) runs: the longest matching path.

        Example::

            >>> GITHUB.command(["issue", "lock", "3"]).paths
            (('issue',),)
        """
        for path, row in self._paths:
            if tuple(words[: len(path)]) == path:
                return row
        return None

    def push_option(self, option: str) -> PushOptionEffect | None:
        """What the git push option ``option`` (``name`` or ``name=value``) does, if anything.

        Example::

            >>> GITLAB.push_option("ci.variable=DEPLOY=1"), GITHUB.push_option("ci.skip")
            ('sets_ci_input', None)
        """
        namespace, dot, key = option.partition("=")[0].partition(".")
        if not dot:
            return None
        namespace = namespace.strip()  # the forge strips each part, as GitLab does
        namespace = dict(self.push_option_aliases).get(namespace, namespace)
        name = f"{namespace}.{key.strip()}"
        return next((effect for known, effect in self.push_options if known == name), None)


def by_cli(argv0: str) -> Forge | None:
    """The forge whose forge CLI is ``argv0`` (a basename), else ``None``.

    Example::

        >>> by_cli("glab").name, by_cli("git")
        ('gitlab', None)
    """
    return next((forge for forge in FORGES if forge.cli == argv0), None)


def by_name(name: str) -> Forge | None:
    """The forge named ``name`` (a ``[forge] hosts`` value), else ``None``.

    Example::

        >>> by_name("github").cli, by_name("GitHub")
        ('gh', None)
    """
    return next((forge for forge in FORGES if forge.name == name), None)


def _flags(text: str) -> frozenset[str]:
    return frozenset(text.split())


_REPO: Final = _flags("-R --repo")
_GH_BODY: Final = _flags("-F --body-file")
_GH_NOTES: Final = _flags("-F --notes-file")
_GLAB_BODY: Final = _flags("--description-file --attach")
_GLAB_NOTES: Final = _flags("-F --notes-file")

GITHUB: Final = Forge(
    name="github",
    host="github.com",
    cli="gh",
    host_env=("GH_HOST",),
    api_host_env=(),
    token_env=("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"),
    repo_flags=_REPO,
    hostname_flags=_flags("--hostname"),
    repo_env=("GH_REPO",),
    repo_host_parts=3,
    snippet_name="gist",
    snippet_host="gist.github.com",
    commands=(
        CliCommand(
            paths=(("gist", "create"), ("gist", "new")),
            options=_flags("-d --desc -f --filename"),
            file_operands=0,
            snippet=True,
        ),
        CliCommand(paths=(("issue",),), options=_REPO, files=_GH_BODY),
        CliCommand(
            paths=(("issue", "create"), ("issue", "new")),
            options=_REPO
            | _flags("-a --assignee -b --body -l --label -m --milestone -p --project --recover")
            | _flags("-t --title -T --template"),
            files=_GH_BODY,
        ),
        CliCommand(
            paths=(("issue", "comment"),), options=_REPO | _flags("-b --body"), files=_GH_BODY
        ),
        CliCommand(
            paths=(("issue", "edit"),),
            options=_REPO
            | _flags("--add-assignee --add-label --add-project --add-sub-issue --add-blocked-by")
            | _flags("--remove-assignee --remove-label --remove-project -b --body")
            | _flags("-m --milestone -t --title"),
            files=_GH_BODY,
        ),
        CliCommand(paths=(("pr",),), options=_REPO, files=_GH_BODY),
        CliCommand(
            paths=(("pr", "create"), ("pr", "new")),
            options=_REPO
            | _flags("-a --assignee -B --base -b --body -H --head -l --label -m --milestone")
            | _flags("-p --project --recover -r --reviewer -t --title -T --template"),
            files=_GH_BODY,
            opens_pull_request=True,
        ),
        CliCommand(paths=(("pr", "comment"),), options=_REPO | _flags("-b --body"), files=_GH_BODY),
        CliCommand(
            paths=(("pr", "edit"),),
            options=_REPO
            | _flags("--add-assignee --add-label --add-project --add-reviewer -B --base -b --body")
            | _flags("--remove-assignee --remove-label --remove-project --remove-reviewer")
            | _flags("-m --milestone -t --title"),
            files=_GH_BODY,
        ),
        CliCommand(paths=(("pr", "review"),), options=_REPO | _flags("-b --body"), files=_GH_BODY),
        CliCommand(paths=(("release",),), options=_REPO, files=_GH_NOTES),
        CliCommand(
            paths=(("release", "create"), ("release", "new")),
            options=_REPO
            | _flags("--discussion-category -n --notes --notes-start-tag --target -t --title"),
            files=_GH_NOTES,
            file_operands=1,
        ),
        CliCommand(paths=(("release", "upload"),), options=_REPO, file_operands=1),
        CliCommand(
            paths=(("api",),),
            options=_flags("--cache -H --header --hostname -q --jq -X --method -p --preview")
            | _flags("-f --raw-field -t --template"),
            files=_flags("--input"),
            field_files=_flags("-F --field"),
        ),
        CliCommand(
            paths=(("repo", "create"), ("repo", "new")),
            options=_flags("-d --description -g --gitignore -h --homepage -l --license")
            | _flags("-r --remote -s --source -t --team -p --template"),
            pushes=_flags("--push"),
            remotes=_flags("-s --source"),
            creates_repository=True,
        ),
        CliCommand(
            paths=(("repo", "fork"),),
            options=_flags("--fork-name --org --remote-name"),
            remotes=_flags("--remote"),
        ),
        CliCommand(
            paths=(("workflow", "run"),),
            options=_REPO | _flags("-f --raw-field -r --ref"),
            field_files=_flags("-F --field"),
        ),
    ),
)

GITLAB: Final = Forge(
    name="gitlab",
    host="gitlab.com",
    cli="glab",
    host_env=("GITLAB_HOST", "GITLAB_URI", "GL_HOST"),
    api_host_env=("GITLAB_API_HOST",),
    token_env=("GITLAB_TOKEN", "GITLAB_ACCESS_TOKEN", "OAUTH_TOKEN"),
    repo_flags=_REPO,
    hostname_flags=_flags("--hostname"),
    repo_env=("GITLAB_REPO",),
    commands=(
        CliCommand(
            paths=(("snippet", "create"), ("snippet", "new")),
            options=_REPO | _flags("-d --description -f --filename -t --title -v --visibility"),
            file_operands=0,
            snippet=True,
        ),
        CliCommand(paths=(("issue",),), options=_REPO, files=_GLAB_BODY),
        CliCommand(
            paths=(("issue", "create"), ("issue", "new")),
            options=_REPO
            | _flags("-a --assignee -d --description --due-date --epic -l --label --link-type")
            | _flags("--linked-issues --linked-mr -m --milestone -e --time-estimate")
            | _flags("-s --time-spent -t --title -w --weight"),
            files=_GLAB_BODY,
            templates=_flags("--template"),
        ),
        CliCommand(
            paths=(("issue", "update"),),
            options=_REPO
            | _flags("-a --assignee -d --description --due-date --estimate -l --label")
            | _flags("-m --milestone --spend -t --title -u --unlabel -w --weight"),
            files=_GLAB_BODY,
        ),
        CliCommand(
            paths=(("issue", "note"), ("issue", "comment")),
            options=_REPO | _flags("-m --message"),
            files=_flags("--attach"),
        ),
        CliCommand(paths=(("mr",),), options=_REPO, files=_GLAB_BODY),
        CliCommand(
            paths=(("mr", "create"), ("mr", "new")),
            options=_REPO
            | _flags("-a --assignee -d --description -H --head -l --label -m --milestone")
            | _flags("-i --related-issue --reviewer -s --source-branch -b --target-branch")
            | _flags("-t --title"),
            files=_GLAB_BODY,
            templates=_flags("--template"),
            # --recover restores a saved push or fill setting (glab 1.115 mr_create.go)
            pushes=_flags("-f --fill --push --recover"),
            opens_pull_request=True,
        ),
        CliCommand(
            paths=(("mr", "update"),),
            options=_REPO
            | _flags("-a --assignee -d --description -l --label -m --milestone --reviewer")
            | _flags("--state --target-branch -t --title -u --unlabel"),
            files=_GLAB_BODY,
        ),
        CliCommand(
            paths=(("mr", "note"), ("mr", "comment"), ("mr", "note", "create")),
            options=_REPO | _flags("--file --line -m --message --old-line --reply"),
            files=_flags("--attach"),
        ),
        CliCommand(paths=(("release",),), options=_REPO, files=_GLAB_NOTES),
        CliCommand(
            paths=(("release", "create"),),
            options=_REPO
            | _flags("-a --assets-links -m --milestone -n --name -N --notes --package-name")
            | _flags("-r --ref -D --released-at -T --tag-message"),
            files=_GLAB_NOTES | _flags("--experimental-notes-text-or-file"),
            file_operands=1,
        ),
        CliCommand(
            paths=(("release", "upload"),),
            options=_REPO | _flags("-a --assets-links --package-name"),
            file_operands=1,
        ),
        CliCommand(
            paths=(("api",),),
            options=_flags("-H --header --hostname -X --method --output --placeholder")
            | _flags("-f --raw-field"),
            files=_flags("--input"),
            field_files=_flags("-F --field --form"),
        ),
        CliCommand(
            paths=(("repo", "create"),),
            options=_flags("--defaultBranch -d --description -g --group -n --name --remoteName")
            | _flags("-t --tag"),
            adds_remote=True,  # git remote add <remoteName>; glab 1.115 has no --push
            creates_repository=True,
        ),
        CliCommand(
            paths=(("repo", "fork"),),
            options=_flags("-n --name -p --path"),
            remotes=_flags("--remote"),
        ),
        CliCommand(
            paths=(("ci", "run"), ("ci", "create")),
            options=_REPO | _flags("-b --branch -i --input --variables --variables-env"),
            files=_flags("-f --variables-from"),
            keyed_files=_flags("--variables-file"),
        ),
        CliCommand(
            paths=(("auth", "login"),),
            options=_flags("-a --api-host -p --api-protocol --container-registry-domains")
            | _flags("-g --git-protocol --hostname --ssh-hostname"),
            secrets=_flags("-t --token -j --job-token"),
        ),
    ),
    push_options=(
        ("secret_push_protection.skip_all", "skips_secret_detection"),
        ("secret_detection.skip_all", "skips_secret_detection"),  # deprecated; GitGuardian reads it
        ("security_policy.bypass_reason", "bypasses_security_policy"),
        ("ci.variable", "sets_ci_input"),
        ("ci.input", "sets_ci_input"),
        ("ci.skip", "skips_ci"),
        ("ci.no_pipeline", "skips_ci"),
        ("integrations.skip_ci", "skips_ci"),
        ("merge_request.create", "opens_pull_request"),
        ("merge_request.description", "sends_text"),
    ),
    push_option_aliases=(("mr", "merge_request"),),
    secret_skip_markers=("[skip secret push protection]", "[skip secret detection]"),
    skip_ci_markers=("[skip ci]", "[ci skip]", "[skip pipeline]", "[no ci]"),
)

FORGES: Final = (GITHUB, GITLAB)
