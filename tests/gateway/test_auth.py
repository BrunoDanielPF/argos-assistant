import pytest

from assistant.gateway.auth import LocalTokenStore, TokenProtectionError


def test_token_is_created_once_with_secure_randomness(tmp_path):
    token_file = tmp_path / "gateway.token"
    protected = []
    store = LocalTokenStore(
        token_file,
        permission_hardener=lambda path: protected.append(path),
    )

    first = store.get_or_create()
    second = store.get_or_create()

    assert first == second
    assert len(first) >= 43
    assert protected == [token_file]


def test_invalid_bearer_token_is_rejected(tmp_path):
    store = LocalTokenStore(
        tmp_path / "gateway.token",
        permission_hardener=lambda path: None,
    )
    token = store.get_or_create()

    assert store.verify(token) is True
    assert store.verify("invalid") is False


def test_token_creation_fails_when_permissions_cannot_be_hardened(tmp_path):
    def fail(_):
        raise OSError("access denied")

    store = LocalTokenStore(
        tmp_path / "gateway.token",
        permission_hardener=fail,
    )

    with pytest.raises(TokenProtectionError):
        store.get_or_create()

    assert not store.path.exists()
