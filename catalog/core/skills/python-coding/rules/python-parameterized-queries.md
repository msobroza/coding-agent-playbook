---
id: python-parameterized-queries
name: Parameterized queries
description: "Never build SQL with string formatting: bind values with the driver's placeholders and take identifiers only from an allow-list."
scope: scoped
globs:
  - "**/*.py"
section: effects
priority: 52
tags: [python, sql, security]
---

# Never build SQL with string formatting

## Description

SQL built with f-strings, `%`, `+` or `.format()` from outside data is injectable, even for values that look harmless such as ids, search terms and sort fields. Pass every value separately and let the driver bind it with its placeholder, so injection is impossible by construction. Identifiers (table, column and sort names) cannot be bound: map the input onto a fixed allow-list.

## Bad Example

```python
def search_users(conn: sqlite3.Connection, term: str, sort: str) -> list[UserRow]:
    query = f"SELECT id, email FROM users WHERE email LIKE '%{term}%' ORDER BY {sort}"
    return [UserRow(*row) for row in conn.execute(query)]
```

## Good Example

```python
class UserSort(Enum):  # the allow-list: each value is SQL this module wrote
    EMAIL = "email"
    NEWEST = "created_at DESC"


def parse_sort(raw: str) -> UserSort:  # the boundary maps outside text onto the allow-list
    try:
        return UserSort[raw.upper()]
    except KeyError:
        allowed = [member.name.lower() for member in UserSort]
        raise InvalidSortError(f"sort must be one of {allowed}, got {raw!r}") from None


def search_users(conn: sqlite3.Connection, term: str, sort: UserSort) -> list[UserRow]:
    query = f"SELECT id, email FROM users WHERE email LIKE ? ORDER BY {sort.value}"
    return [UserRow(*row) for row in conn.execute(query, (f"%{term}%",))]
```

## Notes

- Each driver has its own placeholder: `?` for sqlite3, `%s` (or `%(name)s`) for psycopg, `$1` for asyncpg. Pass the values as the separate parameters argument, never pre-formatted into the string.
- The only text formatted into SQL is a value taken from your own allow-list, as `sort.value` above; a user string never reaches it.
- Bound parameters stop injection, but `%` and `_` inside a `LIKE` pattern are still wildcards; escape them when the term must match literally.
- For an `IN` list, generate one placeholder per value (`", ".join("?" * len(ids))`) and pass the values as parameters.
- Ruff's `S608` flags SQL built from strings.
- With SQLAlchemy, its expressions and `text()` with named parameters bind values; the details are `sqlalchemy-bound-parameters`.
