**Correctness**

- `src/forms.py:43` - important - `kwargs.pop("method", form.method).upper()` breaks callers that pass `method=None`: before this change `FormRequest.from_form(form, method=None)` built a GET request (`Request.__post_init__` maps a missing method to GET), now it raises `AttributeError: 'NoneType' object has no attribute 'upper'`. Pop the keyword first and fall back to the form's method when it is `None`, e.g. `method = (kwargs.pop("method", None) or form.method).upper()`.

Findings: 1 important, 0 nit, 0 pre-existing

request changes
