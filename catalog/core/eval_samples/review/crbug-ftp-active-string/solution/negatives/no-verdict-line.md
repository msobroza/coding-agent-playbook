**Correctness**

- `src/feedstorage.py:27` - important - `-s FEED_STORAGE_FTP_ACTIVE=False` arrives as the string "False", which is truthy; read it with `settings.getbool`.
