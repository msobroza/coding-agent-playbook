import pytest

from src.forms import Form, FormRequest

LOGIN = Form(action="/login", method="post", fields={"user": "alice"})


def test_the_request_uses_the_form_action_and_method() -> None:
    request = FormRequest.from_form(LOGIN)
    assert (request.url, request.method) == ("/login", "POST")


def test_formdata_adds_to_the_form_fields() -> None:
    request = FormRequest.from_form(LOGIN, formdata={"password": "s3cret"})
    assert request.data == {"user": "alice", "password": "s3cret"}


def test_keywords_override_the_form() -> None:
    request = FormRequest.from_form(LOGIN, url="/other", method="GET")
    assert (request.url, request.method) == ("/other", "GET")


@pytest.mark.parametrize("method", FormRequest.valid_form_methods)
def test_valid_form_methods_are_kept(method: str) -> None:
    form = Form(action="/search", method=method.lower())
    assert FormRequest.from_form(form).method == method


def test_an_unknown_form_method_falls_back_to_get() -> None:
    form = Form(action="/search", method="UNKNOWN")
    assert FormRequest.from_form(form).method == "GET"
