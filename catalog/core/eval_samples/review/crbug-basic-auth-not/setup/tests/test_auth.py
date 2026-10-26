from src.auth import Credentials, is_authorized

ADMIN = Credentials("admin", "correct horse")


def test_matching_credentials_are_authorized() -> None:
    assert is_authorized(Credentials("admin", "correct horse"), ADMIN)


def test_a_wrong_password_is_rejected() -> None:
    assert not is_authorized(Credentials("admin", "battery staple"), ADMIN)


def test_a_wrong_username_is_rejected() -> None:
    assert not is_authorized(Credentials("root", "correct horse"), ADMIN)
