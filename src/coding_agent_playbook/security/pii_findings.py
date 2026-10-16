"""PII hits in files, reported like secret findings (specs/prK-hook-pack.md §E.5).

pii-prompt-guard covers prompts only. Its off-workstation twins catch PII
written into files: stop-diff-sweep's PII tier (``config.pii``) and
``playbook scan-secrets --pii``. Both already report masked
:class:`~coding_agent_playbook.security.secrets.SecretFinding` lines (rule,
place and length, never a character of the value), so a PII hit becomes one
too, under rule ``pii:<detector>``: the reports, the pragma handling and the
JSON shape stay as they are. Stdlib only, like both of its modules; the
detectors (``security.pii``) are imported on the first scan, so a sweep with
the PII tier off never loads them.
"""

from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.security.secrets import SecretFinding, is_binary, is_skipped_name

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from coding_agent_playbook.security.pii import PiiConfig
    from coding_agent_playbook.security.secrets import AddedLineLike

__all__ = ["PII_ADVICE", "PII_RULE_PREFIX", "pii_line_findings", "pii_rule_id", "pii_text_findings"]

PII_RULE_PREFIX: Final = "pii:"
PII_ADVICE: Final = "Replace personal data with a placeholder or a synthetic value."
#: Report labels of the engine detectors; an overlay row is labelled by its name.
_LABELS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "iban": "IBAN",
        "card_pan": "payment card number",
        "fr_nir": "French NIR",
        "us_ssn": "US SSN",
    }
)


def pii_rule_id(detector: str) -> str:
    """The finding rule id of a PII detector.

    Example::

        >>> pii_rule_id("iban")
        'pii:iban'
    """
    return f"{PII_RULE_PREFIX}{detector}"


def pii_text_findings(text: str, path: str, cfg: PiiConfig) -> list[SecretFinding]:
    """Every PII value ``cfg`` detects in ``text`` (the whole content of ``path``), in text order.

    Lockfiles and binaries are skipped, as by ``security.secrets.scan_text``.
    Lines are 1-based; a finding holds the length, never the value.

    Example::

        >>> [str(f) for f in pii_text_findings("a\\nGB33BUKB20201555555555", "x.txt", PiiConfig())]
        ['x.txt:2: pii:iban: IBAN (22 chars)']
    """
    if is_skipped_name(path) or is_binary(text):
        return []
    from coding_agent_playbook.security.pii import scan_pii

    findings: list[SecretFinding] = []
    line, counted = 1, 0
    for match in scan_pii(text, cfg):
        line += text.count("\n", counted, match.start)
        counted = match.start
        label = _LABELS.get(match.detector, match.detector)
        findings.append(SecretFinding(pii_rule_id(match.detector), label, path, line, match.length))
    return findings


def pii_line_findings(lines: Iterable[AddedLineLike], cfg: PiiConfig) -> list[SecretFinding]:
    """Every PII value on the added lines of a diff, at each line's new number.

    One scan over the joined lines (no detector matches across a newline).

    Example::

        >>> pii_line_findings([AddedText("a.py", 7, "x = 1")], PiiConfig())
        []
    """
    kept = [line for line in lines if not is_skipped_name(line.path)]
    joined = "\n".join(line.text for line in kept)
    found = pii_text_findings(joined, "", cfg) if kept else []
    return [replace(f, path=kept[f.line - 1].path, line=kept[f.line - 1].line) for f in found]
