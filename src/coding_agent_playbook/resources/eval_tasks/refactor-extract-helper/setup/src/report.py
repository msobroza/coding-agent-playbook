"""A function that begs for a helper extraction.

The ``render_report`` function mixes three concerns: assembling the header,
formatting the totals block, and assembling the footer. The middle block is
the obvious extraction target — it has its own concept, its own complexity,
and no shared state with the rest of the function.
"""

from collections.abc import Iterable


def render_report(title: str, rows: Iterable[tuple[str, int]]) -> str:
    lines: list[str] = [f"# {title}", ""]
    total = 0
    count = 0
    longest_label = 0
    for label, value in rows:
        total += value
        count += 1
        longest_label = max(longest_label, len(label))
        lines.append(f"- {label}: {value}")
    lines.append("")
    lines.append("## Totals")
    lines.append("")
    average = total / count if count else 0
    lines.append(f"- count:    {count}")
    lines.append(f"- total:    {total}")
    lines.append(f"- average:  {average:.2f}")
    padding = " " * (max(0, longest_label - len("widest label")))
    lines.append(f"- widest label{padding}: {longest_label} chars")
    lines.append("")
    lines.append(f"_Report rendered by `render_report` over {count} rows._")
    return "\n".join(lines)
