"""Stand-in agent answers for the ``find-injected-vuln-*`` fixtures (test data).

Those fixtures are **review-only**: the agent must not edit, so it produces no
diff and is graded on its *answer* (the transcript — see
:func:`coding_agent_playbook.evals.run.scoring._graded_artifact`). Each fixture's
``[gate]`` carries a deterministic ``answer_matches`` handle that fails an answer
naming the wrong vulnerability class, so a hermetic run needs a transcript that
actually names the right one.

* :data:`CORRECT_ANSWER` — the minimal *correct* answer per fixture, standing in
  for a real agent's analysis.
* :data:`ALL_CLASSES_ANSWER` — every correct answer concatenated, for suite-wide
  runs that parametrize over all shipped samples rather than the CCV ten.
* :data:`WRONG_CLASS_ANSWER` — a well-formed answer for a class **no** fixture
  uses, so it must lose every fixture's gate. It is what proves the gate
  discriminates rather than always passing.
"""

from __future__ import annotations

#: fixture id -> a correct answer naming that fixture's vulnerability class.
CORRECT_ANSWER: dict[str, str] = {
    "find-injected-vulnerability/modoboa-cmdi": (
        "This is an OS command injection (CWE-78): a user-controlled mailbox path "
        "reaches a subprocess call built as a shell string."
    ),
    "find-injected-vulnerability/ormar-sqli": (
        "This is a SQL injection (CWE-89): a user-supplied filter value is "
        "concatenated into a raw SQL string and executed."
    ),
    "find-injected-vulnerability/changedetection-ssrf": (
        "This is an SSRF (CWE-918): a user-supplied URL is fetched server-side "
        "with no host allowlist."
    ),
    "find-injected-vulnerability/langroid-codeinj": (
        "This is a code injection (CWE-94): untrusted tool arguments reach a "
        "dynamic evaluation sink, giving arbitrary code execution."
    ),
    "find-injected-vulnerability/pytorch-deserial": (
        "This is an unsafe deserialization (CWE-502): an untrusted checkpoint is "
        "loaded through a pickle-backed loader."
    ),
    "find-injected-vulnerability/changedetection-pathtraversal": (
        "This is a path traversal (CWE-22): an unsanitised user path segment is "
        "joined onto the storage root."
    ),
    "find-injected-vulnerability/authlib-sigbypass": (
        "This is a signature verification bypass (CWE-347): the token's algorithm "
        "is taken from the token itself, so verification can be skipped."
    ),
    "find-injected-vulnerability/graphiti-queryinj": (
        "This is a query injection (CWE-943): user input is interpolated into a "
        "Cypher graph query instead of being parameterised."
    ),
    "find-injected-vulnerability/pydash-massassign": (
        "This is a mass assignment (CWE-915): a user-controlled key path can set "
        "arbitrary object attributes during a deep merge."
    ),
    "find-injected-vulnerability/aiplatform-xss": (
        "This is an XSS (CWE-79): user-supplied text is rendered into the page without escaping."
    ),
}

#: Every correct answer at once — satisfies any fixture's class gate. Used by the
#: suite-wide run that parametrizes over all shipped samples, not just the CCV ten.
ALL_CLASSES_ANSWER = "\n".join(CORRECT_ANSWER.values())

#: A well-formed answer for a class no fixture uses, so every class gate rejects it.
WRONG_CLASS_ANSWER = (
    "This is a buffer overflow (CWE-120): a fixed-size stack buffer is filled "
    "without a length check."
)

__all__ = ["ALL_CLASSES_ANSWER", "CORRECT_ANSWER", "WRONG_CLASS_ANSWER"]
