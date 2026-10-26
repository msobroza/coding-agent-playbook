**Correctness**

- `src/feedstorage.py:27` - important - `settings["FEED_STORAGE_FTP_ACTIVE"] or False` keeps the raw value, and command-line overrides are strings (`Settings.from_command_line`): `-s FEED_STORAGE_FTP_ACTIVE=False` yields `"False"`, which is truthy, so the upload switches to active mode, the opposite of what was asked. Use `settings.getbool("FEED_STORAGE_FTP_ACTIVE")`, which already parses True/False and 1/0.

Findings: 1 important, 0 nit, 0 pre-existing

request changes
