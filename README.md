# authgate

A Python auth library that handles JWT token management, password hashing, OAuth2 login flow, and route protection — so you don't have to wire it together yourself.

Most auth libraries do one thing. `PyJWT` gives you JWT encoding. `bcrypt` gives you password hashing. You still have to write the login flow, build the guards, handle the exceptions, and repeat that boilerplate across every project. authgate wraps all of it into one coherent package.

```python
pip install authgate
```

---

## Features

- JWT access and refresh token creation and verification
- Automatic token expiry handling with rotation support
- bcrypt password hashing and verification
- OAuth2 Resource Owner Password Credentials flow
- Decorator-based route/function protection (`@gate.protected`)
- Clean exception hierarchy — catch broadly or specifically
- Framework-agnostic — works with FastAPI, Flask, Django, or plain Python
- Short key warnings to catch insecure configurations early
- Full type hints throughout

---

## Installation

```bash
pip install authgate
```

Requires Python 3.9+.

Dependencies installed automatically: `PyJWT`, `bcrypt`.

---

## Quick Start

```python
from authgate import TokenManager, OAuthHandler, AuthGate, hash_password

# 1. Set up your token manager once
tm = TokenManager(
    secret_key="your-very-secure-secret-key-minimum-32-bytes",
    access_expiry_minutes=15,
    refresh_expiry_days=7
)

# 2. Hash a password at registration
hashed = hash_password("user_plain_password")

# 3. Handle login
def get_user(username):
    # your database lookup here
    return user

oauth = OAuthHandler(token_manager=tm, get_user=get_user)
tokens = oauth.login("john@example.com", "user_plain_password")
# returns {"access_token": "...", "refresh_token": "...", "token_type": "bearer"}

# 4. Protect your routes
gate = AuthGate(token_manager=tm)

@gate.protected
def get_profile(payload=None):
    return f"Hello user {payload['user_id']}"

get_profile(token=tokens["access_token"])
```

---

## Core Concepts

### JWT (JSON Web Token)

A JWT is a self-contained proof of identity. Instead of checking the database on every request to verify a session, the server issues a signed token the client carries around. The server can verify it instantly without any database lookup.

A token has three parts joined by dots: `header.payload.signature`

- **Header** — which algorithm was used to sign it
- **Payload** — the actual data: user id, expiry, token type, any extras
- **Signature** — created by running `HMAC(header + "." + payload, secret_key)`. Anyone can read the payload (it's just base64), but nobody can forge a valid signature without the secret key.

On every request, the server re-runs the HMAC and compares the result to the signature in the token. If they match and the token hasn't expired — it's valid.

### Access vs Refresh Tokens

| | Access Token | Refresh Token |
|---|---|---|
| Lifespan | Short (minutes) | Long (days) |
| Purpose | Authenticate requests | Get a new access token |
| Sent on | Every request | Only when access token expires |

**Rotation** means when a refresh token is used, the server issues a brand new one and the old one should be invalidated. This limits the damage if a refresh token is ever stolen.

### bcrypt

Passwords are one-way hashed — there's no `decode_password()`. bcrypt is intentionally slow (controlled by a cost factor) to make brute force attacks impractical. It generates a random salt per password, embeds it in the hash output, and uses it during verification — so you only ever store one string per password.

---

## API Reference

### `TokenManager`

The core of authgate. Handles all JWT creation and verification. Create one instance and share it across your app.

```python
from authgate import TokenManager

tm = TokenManager(
    secret_key="your-secret-key",
    access_expiry_minutes=15,
    refresh_expiry_days=7
)
```

**Parameters**

| Parameter | Type | Description |
|---|---|---|
| `secret_key` | `str` | Secret used to sign tokens. Minimum 32 bytes recommended. |
| `access_expiry_minutes` | `int` | How long access tokens live, in minutes. |
| `refresh_expiry_days` | `int` | How long refresh tokens live, in days. |

> A `ShortKeyWarning` is issued if your secret key is under 32 bytes. This won't break anything but you should use a longer key in production.

---

#### `create_access_token(user_id, **kwargs) -> str`

Creates a short-lived signed JWT access token.

```python
token = tm.create_access_token(user_id=42)

# with extra claims
token = tm.create_access_token(user_id=42, role="admin", org_id=7)
```

Extra kwargs are embedded in the token payload and available after decoding.

---

#### `create_refresh_token(user_id, **kwargs) -> str`

Creates a long-lived signed JWT refresh token.

```python
token = tm.create_refresh_token(user_id=42)
```

---

#### `decode_token(token) -> dict`

Decodes and verifies a JWT. Returns the payload as a dict on success.

```python
payload = tm.decode_token(token)
# {"user_id": 42, "exp": 1234567890, "type": "access"}
```

**Raises**

| Exception | When |
|---|---|
| `TokenExpiredError` | Token has passed its expiry time |
| `TokenDecodeError` | Token is malformed or has wrong number of segments |
| `InvalidTokenError` | Signature doesn't match — possible tampering |

---

### `OAuthHandler`

Handles the OAuth2 Resource Owner Password Credentials flow. Takes a username and password, verifies them using your user lookup function, and returns a token pair.

```python
from authgate import OAuthHandler

def get_user_from_db(username: str):
    # return a user object with `id` and `hashed_password` attributes
    # return None if user doesn't exist
    return db.query(User).filter(User.email == username).first()

oauth = OAuthHandler(token_manager=tm, get_user=get_user_from_db)
```

**Parameters**

| Parameter | Type | Description |
|---|---|---|
| `token_manager` | `TokenManager` | A configured TokenManager instance. |
| `get_user` | `Callable[[str], Any \| None]` | Function that takes a username and returns a user object or None. |

> Your user object must have `id` and `hashed_password` attributes. If your model uses different field names, add a property:
> ```python
> @property
> def hashed_password(self):
>     return self.password_hash
> ```

---

#### `login(username, password) -> dict`

Authenticates a user and returns an access/refresh token pair.

```python
tokens = oauth.login("john@example.com", "their_password")
# {
#     "access_token": "eyJhbGci...",
#     "refresh_token": "eyJhbGci...",
#     "token_type": "bearer"
# }
```

**Raises**

| Exception | When |
|---|---|
| `InvalidCredentialsError` | No user found with that username |
| `UnauthorizedError` | Password doesn't match the stored hash |
| `GuardError` | Token creation failed unexpectedly |

---

### `AuthGate`

Decorator-based route and function protection. Verifies a JWT before the wrapped function runs and injects the decoded payload as a `payload` keyword argument.

```python
from authgate import AuthGate

gate = AuthGate(token_manager=tm)

@gate.protected
def get_dashboard(payload=None):
    user_id = payload["user_id"]
    return f"Welcome, user {user_id}"

# call it by passing the token
get_dashboard(token="eyJhbGci...")
```

**Parameters**

| Parameter | Type | Description |
|---|---|---|
| `token_manager` | `TokenManager` | A configured TokenManager instance. |

---

#### `protected(f) -> Callable`

Decorator that enforces JWT authentication on the wrapped function.

The wrapped function receives the decoded payload via the `payload` keyword argument. If the token is missing, expired, or invalid, an exception is raised before the function body ever executes.

```python
@gate.protected
def update_settings(new_settings: dict, payload=None):
    user_id = payload["user_id"]
    # safe to proceed
```

**Raises**

| Exception | When |
|---|---|
| `GuardError` | No token provided, token expired, or token can't be decoded |
| `UnauthorizedError` | Token signature is invalid |

---

### `hash_password(plain) -> str`

Hashes a plain text password using bcrypt. Pass this the raw password at registration and store the result in your database.

```python
from authgate import hash_password

hashed = hash_password("user_plain_password")
# "$2b$12$Kq8J3mN..."
```

The result includes the salt embedded in the string — you only need to store this one value.

**Raises** `HashingError` if bcrypt fails unexpectedly.

---

### `verify_password(plain, hashed) -> bool`

Verifies a plain text password against a stored bcrypt hash. Use this at login before issuing tokens.

```python
from authgate import verify_password

is_valid = verify_password("user_plain_password", stored_hash)
# True or False
```

Returns `True` if the password matches, `False` otherwise. Never raises on a wrong password — it just returns `False`. The caller decides what to do with that result.

---

## Exception Handling

All authgate exceptions inherit from `AuthgateError`, so you can catch broadly or specifically depending on what you need.

```
AuthgateError
├── TokenError
│   ├── TokenExpiredError
│   ├── InvalidTokenError
│   └── TokenDecodeError
├── HashingError
└── GuardError
    ├── UnauthorizedError
    └── InvalidCredentialsError
```

All exceptions are importable directly from `authgate`:

```python
from authgate import (
    AuthgateError,
    TokenExpiredError,
    InvalidTokenError,
    TokenDecodeError,
    HashingError,
    GuardError,
    UnauthorizedError,
    InvalidCredentialsError,
)
```

**Catching broadly:**

```python
try:
    tokens = oauth.login(username, password)
except AuthgateError as e:
    return {"error": str(e)}
```

**Catching specifically:**

```python
try:
    payload = tm.decode_token(token)
except TokenExpiredError:
    # tell the client to use their refresh token
    return 401, "token expired"
except InvalidTokenError:
    # token was tampered with
    return 401, "invalid token"
except TokenDecodeError:
    # malformed token
    return 400, "bad token format"
```

---

## Warnings

### `ShortKeyWarning`

Issued when a `TokenManager` is created with a secret key shorter than 32 bytes. HS256 requires at least 32 bytes for adequate security per RFC 7518.

```python
import warnings
from authgate import ShortKeyWarning

# suppress in tests
warnings.filterwarnings("ignore", category=ShortKeyWarning)

# treat as error in CI
warnings.filterwarnings("error", category=ShortKeyWarning)
```

---

## The Full Auth Flow

Here's everything end to end — registration, login, protected route, token refresh.

```python
from authgate import (
    TokenManager, OAuthHandler, AuthGate,
    hash_password, verify_password,
    InvalidCredentialsError, UnauthorizedError, TokenExpiredError
)

# --- App setup (do this once at startup) ---

tm = TokenManager(
    secret_key="your-very-secure-secret-key-minimum-32-bytes",
    access_expiry_minutes=15,
    refresh_expiry_days=7
)

gate = AuthGate(token_manager=tm)

def get_user(username):
    return db.get_user_by_email(username)  # your lookup

oauth = OAuthHandler(token_manager=tm, get_user=get_user)


# --- Registration ---

def register(username, plain_password):
    hashed = hash_password(plain_password)
    db.create_user(username=username, hashed_password=hashed)


# --- Login ---

def login(username, password):
    try:
        return oauth.login(username, password)
    except InvalidCredentialsError:
        return 404, "user not found"
    except UnauthorizedError:
        return 401, "wrong password"


# --- Protected route ---

@gate.protected
def get_profile(payload=None):
    user_id = payload["user_id"]
    return db.get_user(user_id)


# --- Calling a protected route ---

tokens = login("john@example.com", "password123")
profile = get_profile(token=tokens["access_token"])


# --- Token refresh (your responsibility to implement rotation) ---

def refresh(refresh_token):
    try:
        payload = tm.decode_token(refresh_token)
        # invalidate old refresh token in your DB here
        new_access = tm.create_access_token(user_id=payload["user_id"])
        new_refresh = tm.create_refresh_token(user_id=payload["user_id"])
        return {"access_token": new_access, "refresh_token": new_refresh, "token_type": "bearer"}
    except TokenExpiredError:
        return 401, "refresh token expired, please log in again"
```

---

## Project Structure

```
authgate/
├── src/
│   └── authgate/
│       ├── __init__.py       # public API re-exports
│       ├── tokens.py         # JWT access/refresh token management
│       ├── hashing.py        # bcrypt password hashing and verification
│       ├── oauth2.py         # OAuth2 password credentials flow
│       ├── guards.py         # decorator-based route protection
│       ├── exceptions.py     # full exception hierarchy
│       └── warnings.py       # custom warnings
├── tests/
│   ├── test_tokens.py
│   ├── test_hashing.py
│   └── test_guards.py
├── .github/
│   └── workflows/
│       └── publish.yml       # PyPI release pipeline
├── pyproject.toml
├── README.md
└── CHANGELOG.md
```

---

## Design Decisions

**Why framework-agnostic?**

Tying the library to FastAPI or Flask would limit who can use it. The core auth logic — hashing, signing, verifying — has nothing to do with HTTP. Keeping it pure Python means it works anywhere. Framework-specific integrations can be built on top.

**Why a class-based `TokenManager` instead of functions?**

The secret key and expiry settings are configuration — they belong on an instance, not passed into every function call. A class lets you configure once at startup and use everywhere without threading the same arguments through every call.

**Why inject payload via kwargs instead of positional?**

`payload=payload` is explicit — the decorated function always knows where its auth context comes from. Positional injection would break any function whose first argument isn't payload.

**Why re-raise PyJWT and bcrypt exceptions as authgate exceptions?**

So consumers only need to catch authgate exceptions. If we let PyJWT's `ExpiredSignatureError` bubble up, the consumer now has a dependency on PyJWT's internals even if they never installed it directly. Wrapping keeps the public API clean.

---

## Security Considerations

- **Never store plain passwords** — always pass through `hash_password` first
- **Use a secret key of at least 32 bytes** — shorter keys will trigger `ShortKeyWarning`
- **Rotate refresh tokens on every use** — authgate issues new tokens but your application is responsible for invalidating old ones in your database
- **Don't put sensitive data in JWT payloads** — the payload is base64 encoded, not encrypted. Anyone with the token can decode and read it
- **Use HTTPS** — tokens in transit are only as secure as the transport layer
- **Store refresh tokens in httpOnly cookies** — prevents JavaScript access and reduces XSS exposure

---

## Known Limitations

- authgate does not handle refresh token invalidation — that requires a database or cache on your end (store issued refresh tokens and check against them on use)
- No built-in support for RS256 (asymmetric signing) yet — currently HS256 only
- No built-in rate limiting on login attempts
- `AuthGate.protected` assumes token is passed as the first positional argument — may need adjustment depending on your framework's request handling

---

## Future Improvements

- RS256 support for asymmetric key signing
- Built-in token blocklist interface for revocation
- Async-compatible versions of all methods
- FastAPI and Flask integration helpers
- Role-based access control on `AuthGate`

---

## Contributing

Contributions are welcome. Open an issue first to discuss what you'd like to change, especially for anything touching the security-sensitive parts.

```bash
git clone https://github.com/RichardOyelowo/authgate
cd authgate
pip install -e ".[dev]"
pytest
```

---

## License

Apache 2.0 — see [LICENSE](./LICENSE) for details.

---

## Author

Richard Oyelowo — [linkedin.com/in/richard-oyelowo](https://linkedin.com/in/richard-oyelowo)
