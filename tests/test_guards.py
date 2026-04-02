from gatevault import GateVault, TokenManager, OAuthHandler, hash_password
from gatevault.exceptions import GuardError, UnauthorizedError
import pytest

# Test Configuration requirements
class MockUser:
    def __init__(self, id, hashed_password):
        self.id = id
        self.hashed_password = hashed_password

# users database mock
users_test = {"Richard": MockUser(1, hash_password("richard's-password"))}
  
tm = TokenManager("this-should-be-at-least-32bytes-long-for-security", 15, 7)
gate = GateVault(tm)


# ------------- Sync Testing ------------------
# get user function
def get_user(username):
    return users_test.get(username)

handler = OAuthHandler(tm, get_user)

@gate.protected
def get_info(payload=None):
    return payload


# Tests
def test_valid_token():
    # if access tokens works, refresh tokens should
    token = handler.login("Richard", "richard's-password")["access_token"]

    payload = get_info(token=token)
    assert isinstance(payload, dict)
    assert payload.get("user_id") == 1
    assert payload.get("type") == "access"


def test_missing_token():
    with pytest.raises(GuardError):
        payload = get_info()

def test_expired_token():
    tz = TokenManager("this-should-be-at-least-32bytes-long-for-security", 0, 0)
    handler = OAuthHandler(tz, get_user)
    gate = GateVault(tz)

    @gate.protected
    def get_info(payload=None):
        return payload
    
    token = handler.login("Richard", "richard's-password")["access_token"]
    
    with pytest.raises(GuardError):
        payload = get_info(token=token)


def test_tampered_token():
    token = handler.login("Richard", "richard's-password")["access_token"]

    with pytest.raises(UnauthorizedError):
        payload = get_info(token=token + "added_error")


def test_malformed_token():
    with pytest.raises(GuardError):
        payload = get_info(token="this_is-an-invalid-token-for-testing")



# --------------- Async Test --------------------
async def async_get_user(username):
    return users_test.get(username)

async_handler = OAuthHandler(tm, async_get_user)

@gate.protected
async def async_get_info(payload=None):
    return payload



async def test_valid_token_async():
    # if access tokens works, refresh tokens should
    tokens = await async_handler.async_login("Richard", "richard's-password")
    acess_token = tokens["access_token"]

    payload = await async_get_info(token=acess_token)
    assert isinstance(payload, dict)
    assert payload.get("user_id") == 1
    assert payload.get("type") == "access"


async def test_missing_token_async():
    with pytest.raises(GuardError):
        payload = await async_get_info()


async def test_expired_token_async():
    tz = TokenManager("this-should-be-at-least-32bytes-long-for-security", 0, 0)
    async_handler = OAuthHandler(tz, async_get_user)
    gate = GateVault(tz)

    @gate.protected
    async def async_get_info(payload=None):
        return payload
    
    tokens = await async_handler.async_login("Richard", "richard's-password")
    acess_token = tokens["access_token"]
    
    with pytest.raises(GuardError):
        payload = await async_get_info(token=acess_token)


async def test_tampered_token_async():
    tokens = await async_handler.async_login("Richard", "richard's-password")
    acess_token = tokens["access_token"]

    with pytest.raises(UnauthorizedError):
        payload = await async_get_info(token=acess_token + "added_error")


async def test_malformed_token_async():
    with pytest.raises(GuardError):
        payload = await async_get_info(token="this_is-an-invalid-token-for-testing")