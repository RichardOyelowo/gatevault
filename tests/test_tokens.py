import pytest
from uuid import uuid4
from gatevault.exceptions import TokenDecodeError, TokenExpiredError, InvalidTokenError
from gatevault.tokens import TokenManager, normalize_user_id


tm = TokenManager("very-secret-key-preffered-to-be-up-to-32bytes", 15, 7)

def test_create_access_token():
    token = tm.create_access_token(10)
    assert not isinstance(token, bytes)
    assert isinstance(token, str)


def test_create_refresh_token():
    token = tm.create_refresh_token(10)
    assert not isinstance(token, bytes)
    assert isinstance(token, str)


def test_decode_token():
    access_token = tm.create_access_token(10, test="access_token")
    access_payload = tm.decode_token(access_token)

    refresh_token = tm.create_refresh_token(11, test="refresh_token")
    refresh_payload = tm.decode_token(refresh_token)

    # access token & payload assertions
    assert not isinstance(access_payload, str)
    assert isinstance(access_payload, dict)

    assert access_payload["user_id"] == 10
    assert access_payload["test"] == "access_token"

    # refresh tokem & payload asertions
    assert not isinstance(refresh_payload, str)
    assert isinstance(refresh_payload, dict)

    assert refresh_payload["user_id"] == 11
    assert refresh_payload["test"] == "refresh_token"


def test_create_token_with_string_user_id():
    token = tm.create_access_token("user_10")
    payload = tm.decode_token(token)

    assert payload["user_id"] == "user_10"


def test_create_token_with_uuid_user_id():
    user_id = uuid4()

    token = tm.create_access_token(user_id)
    payload = tm.decode_token(token)

    assert payload["user_id"] == str(user_id)


def test_normalize_user_id_rejects_unsupported_type():
    with pytest.raises(TypeError, match="user_id must be int, str, or UUID"):
        normalize_user_id(object())


def test_custom_user_id_encoder_supports_application_id_types():
    class AccountID:
        def __init__(self, value):
            self.value = value

    token_manager = TokenManager(
        "very-secret-key-preffered-to-be-up-to-32bytes",
        15,
        7,
        user_id_encoder=lambda user_id: f"acct_{user_id.value}",
    )

    token = token_manager.create_access_token(AccountID("123"))
    payload = token_manager.decode_token(token)

    assert payload["user_id"] == "acct_123"


def test_custom_user_id_encoder_must_return_string_or_int():
    token_manager = TokenManager(
        "very-secret-key-preffered-to-be-up-to-32bytes",
        15,
        7,
        user_id_encoder=lambda user_id: uuid4(),
    )

    with pytest.raises(TypeError, match="user_id_encoder must return int or str"):
        token_manager.create_access_token(10)


def test_token_decode_error():
    with pytest.raises(TokenDecodeError):
        tm.decode_token("this-is-an-invalid-token")


def test_token_expired_error():
    ta = TokenManager("very-secret-key-up-to-32bytes-for-security", 0, 0)
    token = ta.create_access_token(10)

    with pytest.raises(TokenExpiredError):
        ta.decode_token(token)


def test_invalid_token_error():
    token = tm.create_access_token(10) + "tampered"

    with pytest.raises(InvalidTokenError):
        tm.decode_token(token)
