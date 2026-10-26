"""Store exported feeds on an FTP server."""

from __future__ import annotations

import posixpath
from ftplib import FTP
from typing import BinaryIO

from src.settings import Settings


class FTPFeedStorage:
    """Uploads a finished feed file to a path on an FTP server."""

    def __init__(
        self, host: str, path: str, *, port: int = 21, username: str = "", password: str = "", active: bool = False
    ) -> None:
        self.host = host
        self.path = path
        self.port = port
        self.username = username
        self.password = password
        self.active = active

    @classmethod
    def from_settings(cls, settings: Settings, host: str, path: str) -> FTPFeedStorage:
        return cls(host, path, active=settings["FEED_STORAGE_FTP_ACTIVE"] or False)

    def store(self, file: BinaryIO) -> None:
        file.seek(0)
        ftp = FTP()
        ftp.connect(self.host, self.port)
        ftp.login(self.username, self.password)
        if self.active:
            ftp.set_pasv(False)
        dirname, filename = posixpath.split(self.path)
        ftp.cwd(dirname)
        ftp.storbinary(f"STOR {filename}", file)
        ftp.quit()
