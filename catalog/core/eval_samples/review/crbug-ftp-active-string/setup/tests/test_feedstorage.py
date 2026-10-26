from src.feedstorage import FTPFeedStorage
from src.settings import Settings

HOST, PATH = "ftp.example.com", "/feeds/items.json"


def test_the_storage_targets_the_host_and_path_on_port_21() -> None:
    storage = FTPFeedStorage.from_settings(Settings(), HOST, PATH)
    assert (storage.host, storage.port, storage.path) == (HOST, 21, PATH)


def test_passive_mode_is_the_default() -> None:
    assert FTPFeedStorage.from_settings(Settings(), HOST, PATH).active is False


def test_the_setting_turns_active_mode_on() -> None:
    settings = Settings({"FEED_STORAGE_FTP_ACTIVE": True})
    assert FTPFeedStorage.from_settings(settings, HOST, PATH).active is True
