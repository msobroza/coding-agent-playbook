"""GitHub alert blocks rewritten as MyST admonitions (docs/_ext/github_alerts.py)."""

from __future__ import annotations

import pytest

from github_alerts import ALERT_DIRECTIVES, alerts_to_admonitions


@pytest.mark.parametrize(("kind", "directive"), sorted(ALERT_DIRECTIVES.items()))
def test_each_alert_kind_becomes_its_admonition(kind: str, directive: str) -> None:
    text = f"Intro.\n\n> [!{kind}]\n> First line.\n> Second line.\n\nAfter.\n"

    assert alerts_to_admonitions(text) == (
        f"Intro.\n\n:::{{{directive}}}\nFirst line.\nSecond line.\n:::\n\nAfter.\n"
    )


def test_a_code_block_inside_an_alert_is_kept() -> None:
    text = "> [!TIP]\n> Run:\n>\n> ```bash\n> playbook sync\n> ```\n"

    assert alerts_to_admonitions(text) == (":::{tip}\nRun:\n\n```bash\nplaybook sync\n```\n:::\n")


@pytest.mark.parametrize(
    "text",
    [
        "> A plain quote stays a quote.\n",
        "> [!UNKNOWN]\n> Not an alert kind GitHub knows.\n",
        "```markdown\n> [!NOTE]\n> An example inside a code fence.\n```\n",
    ],
)
def test_other_text_is_left_alone(text: str) -> None:
    assert alerts_to_admonitions(text) == text
