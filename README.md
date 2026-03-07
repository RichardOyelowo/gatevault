# authgate

A Python auth library that handles JWT token management, password hashing, OAuth2 login flow, and route protection — so you don't have to wire it together yourself.

Most auth libraries do one thing. `PyJWT` gives you JWT encoding. `bcrypt` gives you password hashing. You still have to write the login flow, build the guards, handle the exceptions, and repeat that boilerplate across every project. authgate wraps all of it into one coherent package with a clean API you can drop into any Python project regardless of framework.

```bash
pip install authgate
```

---

## Table of Contents

- [Installation](#installation)
- [The Full Picture](#the-full-picture)
- [Password Hashing](#password-hashing)
- [Token Management](#token-management)
- [Login Flow](#login-flow)
- [Protecting Routes](#protecting-routes)
- [Exception Handling](#exception-handling)
- [Warnings](#warnings)
- [Framework Integration](#framework-integration)
  - [FastAPI](#fastapi)
  - [Flask](#flask)
- [Using authgate in Parts](#using-authgate-in-parts)
  - [Just Hashing](#just-hashing)
  - [Just Tokens](#just-tokens)
  - [Just Guards](#just-guards)
- [Token Refresh & Rotation](#token-refresh--rotation)
- [Security Guide](#security-guide)
- [API Reference](#api-reference)
- [Design Decisions](#design-decisions)
- [Known Limitations](#known-limitations)
- [Future Improvements](#future-improvements)
- [Contributing](#contributing)
- [License](#license)

---

## Installation

```bash
pip install authgate
```

Requires Python 3.9+. Dependencies `PyJWT` and `bcrypt` are installed automatically.

Everything in authgate is importable from the top level:

```python
from authgate import (
    TokenManager,
    OAuthHandler,
    AuthGate,
    hash_password,
    verify_password,
)
```

---

## The Full Picture

Before going into each feature, here is what a complete auth setup looks like from registration to protected route access. If you only need one specific feature, jump to the relevant section.

```python
from authgate import (
    TokenManager, OAuthHandler, AuthGate,
    hash_password, verify_password,
    InvalidCredentialsError, UnauthorizedError, TokenExpiredError
)

# --- Setup (once at app startup) ---

tm = TokenManager(
    secret_key="your-very-secure-secret-key-minimum-32-bytes",
    access_expiry_minutes=15,
    refresh_expiry_days=7
)

gate = AuthGate(token_manager=tm)

def get_user(username):
    return db.get_user_by_email(username)  # your own lookup

oauth = OAuthHandler(token_manager=tm, get_user=get_user)


# --- Registration ---

def register(username, plain_password):
    hashed = hash_password(plain_password)
    db.create_user(username=username, hashed_password=hashed)


# --- Login ---

def login(username, password):
    try:
        return oauth.login(username, password)
        # {"access_token": "...", "refresh_token": "...", "token_type": "bearer"}
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
```

---

## Password Hashing

authgate uses bcrypt for password hashing. Passwords are one-way hashed — there is no way to reverse a hash back to the original password. This is intentional. If your database is ever compromised, attackers get hashes, not passwords.

### Hashing a password

```python
from authgate import hash_password

hashed = hash_password("user_plain_password")
print(hashed)
# $2b$12$Kq8J3mNrandom...
```

Always hash at the point of registration and store the result. Never store or log the plain password.

```python
# At registration
def create_account(username, plain_password):
    hashed = hash_password(plain_password)
    db.insert(username=username, password=hashed)
```

### Verifying a password

```python
from authgate import verify_password

is_match = verify_password("user_plain_password", stored_hash)
# True or False
```

`verify_password` returns a boolean. It never raises on a wrong password — it just returns `False`. What you do with that result is your decision.

```python
# At login
def authenticate(username, plain_password):
    user = db.get_user(username)
    if not user:
        raise InvalidCredentialsError("user not found")
    if not verify_password(plain_password, user.hashed_password):
        raise UnauthorizedError("wrong password")
    return user
```

### About bcrypt salting

You do not need to manage salts yourself. bcrypt generates a unique random salt for every hash and embeds it in the output string. Two calls to `hash_password` with the same password produce different hashes — both are valid. `verify_password` extracts the salt automatically from the stored hash during verification.

```python
h1 = hash_password("same_password")
h2 = hash_password("same_password")
print(h1 == h2)  # False — different salts, both valid
print(verify_password("same_password", h1))  # True
print(verify_password("same_password", h2))  # True
```

---

## Token Management

`TokenManager` handles all JWT creation and verification. It is the core of authgate. Create one instance at startup and share it across your app.

### Setup

```python
from authgate import TokenManager

tm = TokenManager(
    secret_key="your-very-secure-secret-key-minimum-32-bytes",
    access_expiry_minutes=15,
    refresh_expiry_days=7
)
```

The `secret_key` is what signs your tokens. Anyone with this key can create valid tokens, so keep it secret and never commit it to source control. Use an environment variable:

```python
import os
from authgate import TokenManager

tm = TokenManager(
    secret_key=os.environ["AUTH_SECRET_KEY"],
    access_expiry_minutes=int(os.environ.get("ACCESS_EXPIRY_MINUTES", 15)),
    refresh_expiry_days=int(os.environ.get("REFRESH_EXPIRY_DAYS", 7))
)
```

### Creating tokens

```python
access_token = tm.create_access_token(user_id=42)
refresh_token = tm.create_refresh_token(user_id=42)
```

Both methods return a JWT string. Access tokens are short-lived — meant to be sent with every authenticated request. Refresh tokens are long-lived — used only to obtain a new access token when the current one expires.

### Extra claims

You can embed additional data in the token payload using keyword arguments:

```python
token = tm.create_access_token(user_id=42, role="admin", org_id=7)

payload = tm.decode_token(token)
print(payload)
# {"user_id": 42, "exp": 1234567890, "type": "access", "role": "admin", "org_id": 7}
```

This is useful for embedding role or permission data so your guards can make access decisions without hitting the database on every request.

### Decoding tokens

```python
payload = tm.decode_token(token)
user_id = payload["user_id"]
token_type = payload["type"]  # "access" or "refresh"
```

`decode_token` verifies the signature and checks expiry automatically. It raises specific exceptions on failure rather than returning `None` or a status code — so you know exactly what went wrong.

```python
from authgate import TokenExpiredError, InvalidTokenError, TokenDecodeError

try:
    payload = tm.decode_token(token)
except TokenExpiredError:
    # send the client to the refresh endpoint
    pass
except InvalidTokenError:
    # signature mismatch — possible tampering
    pass
except TokenDecodeError:
    # malformed token string
    pass
```

### Access vs refresh — tell them apart

Every token has a `type` claim embedded in the payload. Check it if you need to enforce which kind of token is being used:

```python
payload = tm.decode_token(token)

if payload["type"] != "access":
    raise UnauthorizedError("expected an access token")
```

This prevents someone from using a refresh token where an access token is expected.

---

## Login Flow

`OAuthHandler` wires together user lookup, password verification, and token creation into one call. It follows the OAuth2 Resource Owner Password Credentials flow.

### Setup

```python
from authgate import OAuthHandler

def get_user(username: str):
    # return a user object with `id` and `hashed_password` attributes
    # return None if user does not exist
    return db.query(User).filter(User.email == username).first()

oauth = OAuthHandler(token_manager=tm, get_user=get_user)
```

Your `get_user` function must return an object with two attributes:
- `id` — the user's identifier, passed into the token payload
- `hashed_password` — the bcrypt hash stored at registration

If your model uses different field names, add a property:

```python
class User:
    # your model fields...

    @property
    def hashed_password(self):
        return self.password_hash  # whatever your field is called
```

### Logging in

```python
tokens = oauth.login("john@example.com", "their_password")
print(tokens)
# {
#     "access_token": "eyJhbGci...",
#     "refresh_token": "eyJhbGci...",
#     "token_type": "bearer"
# }
```

`login` does three things in order:
1. Calls `get_user(username)` — raises `InvalidCredentialsError` if it returns `None`
2. Calls `verify_password` — raises `UnauthorizedError` if the password does not match
3. Creates and returns both tokens

### Handling login errors

```python
from authgate import InvalidCredentialsError, UnauthorizedError, GuardError

try:
    tokens = oauth.login(username, password)
except InvalidCredentialsError:
    return {"error": "Invalid credentials"}, 401
except UnauthorizedError:
    return {"error": "Invalid credentials"}, 401
except GuardError:
    return {"error": "Authentication failed"}, 500
```

Note: returning the same error message for both `InvalidCredentialsError` and `UnauthorizedError` is intentional. Telling an attacker which one failed helps them enumerate valid usernames.

---

## Protecting Routes

`AuthGate` is a decorator factory that wraps any function with token verification. The wrapped function never executes if the token is missing, expired, or invalid.

### Setup

```python
from authgate import AuthGate

gate = AuthGate(token_manager=tm)
```

### Basic usage

```python
@gate.protected
def get_profile(payload=None):
    user_id = payload["user_id"]
    return db.get_user(user_id)

# call the function by passing the token
result = get_profile(token="eyJhbGci...")
```

The decoded payload is injected as the `payload` keyword argument. Declaring `payload=None` as a default is a good habit so the function signature is clear.

### Accessing claims from the payload

```python
@gate.protected
def admin_only(payload=None):
    if payload.get("role") != "admin":
        raise UnauthorizedError("admin access required")
    return get_admin_data()
```

Any extra claims embedded at token creation time are available in the payload here.

### Passing other arguments

The guard passes through any additional arguments to your function untouched:

```python
@gate.protected
def get_post(post_id: int, payload=None):
    user_id = payload["user_id"]
    post = db.get_post(post_id)
    if post.owner_id != user_id:
        raise UnauthorizedError("not your post")
    return post

get_post(post_id=7, token="eyJhbGci...")
```

### Handling guard errors

```python
from authgate import GuardError, UnauthorizedError

try:
    result = get_profile(token=incoming_token)
except GuardError as e:
    return {"error": str(e)}, 401
except UnauthorizedError as e:
    return {"error": str(e)}, 401
```

---

## Exception Handling

All authgate exceptions inherit from `AuthgateError`. You can catch at any level of the hierarchy depending on how granular your error handling needs to be.

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

### Importing exceptions

```python
from authgate import (
    AuthgateError,
    TokenError,
    TokenExpiredError,
    InvalidTokenError,
    TokenDecodeError,
    HashingError,
    GuardError,
    UnauthorizedError,
    InvalidCredentialsError,
)
```

### Catching broadly

```python
try:
    tokens = oauth.login(username, password)
except AuthgateError as e:
    return {"error": str(e)}, 401
```

### Catching specifically

```python
try:
    payload = tm.decode_token(token)
except TokenExpiredError:
    return {"error": "token expired"}, 401
except InvalidTokenError:
    return {"error": "invalid token"}, 401
except TokenDecodeError:
    return {"error": "malformed token"}, 400
```

### Catching by category

```python
try:
    payload = tm.decode_token(token)
except TokenError:
    # catches TokenExpiredError, InvalidTokenError, and TokenDecodeError
    return {"error": "token error"}, 401
```

---

## Warnings

### `ShortKeyWarning`

Issued at `TokenManager` creation if the secret key is shorter than 32 bytes. HS256 requires at least 32 bytes for adequate security per RFC 7518. This is a warning, not an error — your app will still run, but you should use a longer key in production.

```python
import warnings
from authgate import ShortKeyWarning

# suppress in tests
warnings.filterwarnings("ignore", category=ShortKeyWarning)

# treat as a hard error in CI to catch misconfigurations early
warnings.filterwarnings("error", category=ShortKeyWarning)
```

To generate a secure key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Framework Integration

authgate is framework-agnostic but slots naturally into FastAPI and Flask.

### FastAPI

```python
import os
from fastapi import FastAPI, Header, HTTPException
from authgate import TokenManager, OAuthHandler, AuthGate, hash_password
from authgate import InvalidCredentialsError, UnauthorizedError, GuardError, TokenExpiredError

app = FastAPI()

tm = TokenManager(
    secret_key=os.environ["AUTH_SECRET_KEY"],
    access_expiry_minutes=15,
    refresh_expiry_days=7
)

gate = AuthGate(token_manager=tm)
oauth = OAuthHandler(token_manager=tm, get_user=get_user_from_db)


@app.post("/register")
def register(username: str, password: str):
    hashed = hash_password(password)
    db.create_user(username=username, hashed_password=hashed)
    return {"message": "registered"}


@app.post("/login")
def login(username: str, password: str):
    try:
        return oauth.login(username, password)
    except (InvalidCredentialsError, UnauthorizedError):
        raise HTTPException(status_code=401, detail="Invalid credentials")


@app.get("/profile")
def profile(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")

    @gate.protected
    def _inner(payload=None):
        return {"user_id": payload["user_id"]}

    try:
        return _inner(token=token)
    except (GuardError, UnauthorizedError):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.post("/refresh")
def refresh(refresh_token: str):
    try:
        payload = tm.decode_token(refresh_token)
        if payload["type"] != "refresh":
            raise HTTPException(status_code=400, detail="expected refresh token")
        new_access = tm.create_access_token(user_id=payload["user_id"])
        new_refresh = tm.create_refresh_token(user_id=payload["user_id"])
        return {"access_token": new_access, "refresh_token": new_refresh, "token_type": "bearer"}
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="refresh token expired")
```

### Flask

```python
import os
from flask import Flask, request, jsonify
from authgate import TokenManager, OAuthHandler, AuthGate, hash_password
from authgate import InvalidCredentialsError, UnauthorizedError, GuardError

app = Flask(__name__)

tm = TokenManager(
    secret_key=os.environ["AUTH_SECRET_KEY"],
    access_expiry_minutes=15,
    refresh_expiry_days=7
)

gate = AuthGate(token_manager=tm)
oauth = OAuthHandler(token_manager=tm, get_user=get_user_from_db)


def get_token_from_request():
    auth = request.headers.get("Authorization", "")
    return auth.replace("Bearer ", "")


@app.post("/register")
def register():
    data = request.json
    hashed = hash_password(data["password"])
    db.create_user(username=data["username"], hashed_password=hashed)
    return jsonify({"message": "registered"})


@app.post("/login")
def login():
    data = request.json
    try:
        tokens = oauth.login(data["username"], data["password"])
        return jsonify(tokens)
    except (InvalidCredentialsError, UnauthorizedError):
        return jsonify({"error": "invalid credentials"}), 401


@app.get("/profile")
def profile():
    token = get_token_from_request()

    @gate.protected
    def _inner(payload=None):
        return jsonify({"user_id": payload["user_id"]})

    try:
        return _inner(token=token)
    except (GuardError, UnauthorizedError):
        return jsonify({"error": "unauthorized"}), 401
```

---

## Using authgate in Parts

You do not have to use the whole package. Each part is independent and works on its own.

### Just Hashing

No tokens, no guards — just password hashing and verification:

```python
from authgate import hash_password, verify_password

# at registration
hashed = hash_password("user_password")
db.save(hashed)

# at login
if verify_password("user_password", db.get_hash(user_id)):
    # proceed with login
    pass
```

No other setup needed. `hash_password` and `verify_password` are standalone functions with no dependencies on the rest of the package.

---

### Just Tokens

If you have your own login and auth flow and only want JWT management:

```python
from authgate import TokenManager
from authgate import TokenExpiredError, InvalidTokenError, TokenDecodeError

tm = TokenManager(
    secret_key="your-secret",
    access_expiry_minutes=30,
    refresh_expiry_days=14
)

# issue tokens however you like
access = tm.create_access_token(user_id=1)
refresh = tm.create_refresh_token(user_id=1)

# with extra claims
access = tm.create_access_token(user_id=1, role="admin")

# decode later
try:
    payload = tm.decode_token(access)
    print(payload["user_id"], payload["role"])
except TokenExpiredError:
    pass
except InvalidTokenError:
    pass
```

---

### Just Guards

If you already have tokens from your own system and just want decorator-based protection:

```python
from authgate import TokenManager, AuthGate
from authgate import GuardError, UnauthorizedError

tm = TokenManager(
    secret_key="your-secret",
    access_expiry_minutes=15,
    refresh_expiry_days=7
)
gate = AuthGate(token_manager=tm)

@gate.protected
def sensitive_action(data: dict, payload=None):
    user_id = payload["user_id"]
    return process(data, user_id)

try:
    result = sensitive_action(data={"key": "value"}, token=incoming_token)
except (GuardError, UnauthorizedError):
    return 401
```

---

## Token Refresh & Rotation

authgate creates new tokens on demand but does not manage token storage or invalidation — that lives in your application. Here is the recommended pattern:

### The refresh flow

```python
from authgate import TokenExpiredError, InvalidTokenError, TokenDecodeError

def refresh_tokens(refresh_token: str):
    try:
        payload = tm.decode_token(refresh_token)
    except TokenExpiredError:
        # refresh token expired — force re-login
        return {"error": "session expired"}, 401
    except (InvalidTokenError, TokenDecodeError):
        return {"error": "invalid token"}, 401

    if payload["type"] != "refresh":
        return {"error": "wrong token type"}, 400

    # invalidate the old refresh token in your database
    db.revoke_refresh_token(refresh_token)

    # issue a new pair
    new_access = tm.create_access_token(user_id=payload["user_id"])
    new_refresh = tm.create_refresh_token(user_id=payload["user_id"])

    # store the new refresh token
    db.store_refresh_token(new_refresh, user_id=payload["user_id"])

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer"
    }
```

### Why rotation matters

Without rotation, a stolen refresh token is valid until it expires — potentially days. With rotation, every use of the refresh token produces a new one and the old one is revoked. If a stolen token is used, the legitimate user's next refresh attempt will fail because their token was already rotated, alerting them that something is wrong.

---

## Security Guide

### Secret key

- Use at least 32 bytes — authgate will warn you if you don't
- Generate with `python -c "import secrets; print(secrets.token_hex(32))"`
- Never hardcode it — use environment variables
- Rotate it only when necessary — rotation invalidates all existing tokens immediately

### Token storage on the client

- **Access token** — store in memory (a JS variable). Short-lived so the exposure window is small. Do not store in localStorage.
- **Refresh token** — store in an httpOnly cookie. httpOnly prevents JavaScript from reading it, which reduces XSS exposure. Send it only to your refresh endpoint, never on regular requests.

### What not to put in a token payload

The payload is base64 encoded, not encrypted. Anyone with the token string can decode and read it. Never put passwords, credit card numbers, or any sensitive data in the payload. `user_id`, `role`, and `org_id` are fine.

### Refresh token revocation

Tokens cannot be invalidated once issued — that is a fundamental property of stateless JWTs. If you need true revocation (e.g. logout, password change, suspicious activity), maintain a blocklist in your database or cache and check against it in your refresh endpoint or guard logic.

### Login enumeration

When a login fails, return the same error message whether the username does not exist or the password is wrong. Distinguishing between the two tells an attacker which usernames are valid accounts.

---

## API Reference

### `TokenManager(secret_key, access_expiry_minutes, refresh_expiry_days)`

| Parameter | Type | Description |
|---|---|---|
| `secret_key` | `str` | Secret for signing tokens. Minimum 32 bytes recommended. |
| `access_expiry_minutes` | `int` | Access token lifetime in minutes. |
| `refresh_expiry_days` | `int` | Refresh token lifetime in days. |

| Method | Returns | Description |
|---|---|---|
| `create_access_token(user_id, **kwargs)` | `str` | Creates a signed access token. Extra kwargs embedded in payload. |
| `create_refresh_token(user_id, **kwargs)` | `str` | Creates a signed refresh token. Extra kwargs embedded in payload. |
| `decode_token(token)` | `dict` | Verifies and decodes a token. Raises on failure. |

---

### `OAuthHandler(token_manager, get_user)`

| Parameter | Type | Description |
|---|---|---|
| `token_manager` | `TokenManager` | Configured TokenManager instance. |
| `get_user` | `Callable[[str], Any \| None]` | User lookup function. Must return object with `id` and `hashed_password`, or `None`. |

| Method | Returns | Description |
|---|---|---|
| `login(username, password)` | `dict` | Authenticates user and returns access/refresh token pair. |

---

### `AuthGate(token_manager)`

| Parameter | Type | Description |
|---|---|---|
| `token_manager` | `TokenManager` | Configured TokenManager instance. |

| Method | Returns | Description |
|---|---|---|
| `protected(f)` | `Callable` | Decorator. Verifies token before function runs, injects payload as kwarg. |

---

### `hash_password(plain) -> str`

| Parameter | Type | Description |
|---|---|---|
| `plain` | `str` | Plain text password. Pass the raw string — encoding is handled internally. |

Returns the bcrypt hash as a string. Raises `HashingError` if bcrypt fails unexpectedly.

---

### `verify_password(plain, hashed) -> bool`

| Parameter | Type | Description |
|---|---|---|
| `plain` | `str` | Plain text password to check. |
| `hashed` | `str` | Stored bcrypt hash to check against. |

Returns `True` if the password matches, `False` otherwise. Never raises on a wrong password.

---

## Design Decisions

**Framework-agnostic**

Tying authgate to FastAPI or Flask would limit who can use it. The core auth logic — hashing, signing, verifying — has nothing to do with HTTP. Keeping it pure Python means it works anywhere and framework-specific integrations can be layered on top.

**Class-based `TokenManager` instead of functions**

The secret key and expiry settings are configuration — they belong on an instance, not passed into every function call. Configure once at startup, use everywhere.

**Payload injected as a keyword argument**

`payload=payload` is explicit. The decorated function always knows where its auth context comes from and can choose to accept it or ignore it. Positional injection would silently break functions whose arguments do not match the expected order.

**Wrapping third-party exceptions**

`PyJWT` and `bcrypt` exceptions never leak through the authgate API. Consumers only need to know authgate exceptions. If an underlying library changes its exception names in a future version, only authgate updates — not every app built on it.

**`verify_password` returns bool, not raises**

A wrong password is an expected outcome, not an exceptional one. The caller decides what to do — raise, log, increment a failed attempt counter, or something else.

---

## Known Limitations

- Refresh token invalidation is not handled by authgate — you need a database or cache to track and revoke issued refresh tokens
- Only HS256 (symmetric) signing is supported — RS256 (asymmetric keypair) is not yet available
- `AuthGate.protected` expects the token as a keyword argument — you may need a thin adapter in frameworks that inject request objects differently
- No built-in rate limiting on login attempts — implement this at the application or infrastructure level

---

## Future Improvements

- RS256 support for asymmetric key signing
- Built-in token blocklist interface for revocation
- Async-compatible versions of all methods
- Role-based access control helpers on `AuthGate`
- FastAPI and Flask integration packages

---

## Contributing

Contributions are welcome. Open an issue first to discuss what you want to change, especially for anything touching the security-sensitive parts.

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

*Built by Richard for the love of development.*
