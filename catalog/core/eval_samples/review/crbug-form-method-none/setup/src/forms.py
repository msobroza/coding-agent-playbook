"""Build the request that submits an HTML form found in a fetched page."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Form:
    """A parsed ``<form>``: its action URL, its method attribute and its fields."""

    action: str
    method: str
    fields: dict[str, str] = field(default_factory=dict)


@dataclass
class Request:
    """An outgoing HTTP request; a missing method means GET."""

    url: str
    method: str | None = "GET"
    data: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.method = (self.method or "GET").upper()


class FormRequest(Request):
    """A request that submits a form."""

    valid_form_methods = ["GET", "POST"]

    @classmethod
    def from_form(
        cls, form: Form, formdata: dict[str, str] | None = None, **kwargs: Any
    ) -> FormRequest:
        """The request submitting ``form``; ``url`` and ``method`` keywords override the form's."""
        data = {**form.fields, **(formdata or {})}
        url = kwargs.pop("url", None) or form.action

        method = kwargs.pop("method", form.method).upper()
        if method not in cls.valid_form_methods:
            method = "GET"

        return cls(url=url, method=method, data=data, **kwargs)
