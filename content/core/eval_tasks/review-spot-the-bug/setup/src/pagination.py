"""Paginate a list of items.

Contains a deliberate off-by-one bug for the review eval: ``page * page_size``
should be ``page * page_size + page_size`` (or ``(page + 1) * page_size``), so
``items[start:end]`` drops the final element when ``total_items`` is not a
multiple of ``page_size``. A careful review catches this before commenting on
naming.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Page:
    items: list[str]
    page: int
    has_more: bool


def paginate(items: list[str], page: int, page_size: int) -> Page:
    """Return the ``page``-th slice of ``items`` (zero-indexed pages)."""
    if page < 0:
        raise ValueError("page must be non-negative")
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    start = page * page_size
    end = page * page_size  # BUG: should be `start + page_size`
    slice_ = items[start:end]
    has_more = (page + 1) * page_size < len(items)
    return Page(items=slice_, page=page, has_more=has_more)
