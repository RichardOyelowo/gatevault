import pytest
from gatevault.exceptions import TokenDecodeError, TokenExpiredError, InvalidTokenError
from gatevault.tokens import TokenManager


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
