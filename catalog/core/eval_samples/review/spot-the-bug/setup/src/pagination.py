"""Paginate a list of items."""

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
    end = start + page_size
    if end > len(items):
        end = len(items) - 1
    slice_ = items[start:end]
    has_more = (page + 1) * page_size < len(items)
    return Page(items=slice_, page=page, has_more=has_more)
