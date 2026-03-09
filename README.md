# <img src="https://raw.githubusercontent.com/RichardOyelowo/gatevault/main/images/white_logo.png">

<p align="center">
  <a href="https://pypi.org/project/richard-gatevault/"><img src="https://img.shields.io/pypi/v/richard-gatevault?color=8B4513&label=pypi&style=flat-square"></a>
  <a href="https://pypi.org/project/richard-gatevault/"><img src="https://img.shields.io/pypi/pyversions/richard-gatevault?color=3776AB&style=flat-square"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-orange?style=flat-square"></a>
  <a href="https://github.com/RichardOyelowo/gatevault/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/RichardOyelowo/gatevault/ci.yml?label=CI&style=flat-square"></a>
  <a href="https://linkedin.com/in/richard-oyelowo"><img src="https://img.shields.io/badge/LinkedIn-Richard%20Oyelowo-0077B5?logo=linkedin&style=flat-square"></a>
</p>

---

A Python auth library that handles JWT token management, password hashing, OAuth2 login flow, and route protection — so you don't have to wire it together yourself.

Most auth libraries do one thing. `PyJWT` gives you JWT encoding. `bcrypt` gives you password hashing. You still have to write the login flow, build the guards, handle the exceptions, and repeat that boilerplate across every project. gatevault wraps all of it into one coherent package with a clean API you can drop into any Python project regardless of framework.

```bash
pip install richard-gatevault
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
- [Using gatevault in Parts](#using-gatevault-in-parts)
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
pip install richard-gatevault
```

Requires Python 3.9+. Dependencies `PyJWT` and `bcrypt` are installed automatically.

Everything in gatevault is importable from the top level:

```python
from gatevault import (
    TokenManager,
    OAuthHandler,
    GateVault,
    hash_password,
    verify_password,
)
```

---

## The Full Picture

Here is what a complete auth setup looks like end to end — registration, login, token storage, protected routes, and token refresh. If you only need one specific feature, jump to the relevant section.

```python
import os
from gatevault import (
    TokenManager, OAuthHandler, GateVault,
    hash_password, verify_password,
    InvalidCredentialsError, UnauthorizedError,
    TokenExpiredError, GuardError
)

# ---------------------------------------------------------------------------
# Setup — do this once at app startup
# ---------------------------------------------------------------------------

tm = TokenManager(
    secret_key=os.environ["AUTH_SECRET_KEY"],
    access_expiry_minutes=15,
    refresh_expiry_days=7
)

gate = GateVault(token_manager=tm)
oauth = OAuthHandler(token_manager=tm, get_user=get_user_from_db)


# ---------------------------------------------------------------------------
# Registration — hash and store the password
# ---------------------------------------------------------------------------

def register(username: str, plain_password: str):
    hashed = hash_password(plain_password)
    db.create_user(username=username, hashed_password=hashed)
    return {"message": "registered"}


# ---------------------------------------------------------------------------
# Login — returns access token in body, refresh token goes in httpOnly cookie
#
# The client stores the access token in memory (a JS variable).
# The refresh token is stored in an httpOnly cookie — it cannot be read
# by JavaScript, which reduces XSS exposure.
# ---------------------------------------------------------------------------

def login(username: str, password: str):
    try:
        tokens = oauth.login(username, password)
    except (InvalidCredentialsError, UnauthorizedError):
        return {"error": "invalid credentials"}, 401

    # In a real app, set the refresh token as an httpOnly cookie:
    # response.set_cookie("refresh_token", tokens["refresh_token"], httponly=True)
    #
    # Return only the access token in the response body:
    return {"access_token": tokens["access_token"]}


# ---------------------------------------------------------------------------
# Protected functions — decorated once, reused across many routes
# ---------------------------------------------------------------------------

@gate.protected
def get_profile(payload=None):
    user_id = payload["user_id"]
    return db.get_user(user_id)

@gate.protected
def get_orders(payload=None):
    user_id = payload["user_id"]
    return db.get_orders(user_id)

@gate.protected
def update_settings(settings: dict, payload=None):
    user_id = payload["user_id"]
    return db.update_settings(user_id, settings)


# ---------------------------------------------------------------------------
# Routes — the framework extracts the token from the Authorization header
# and passes it to the protected function
#
# Client sends: Authorization: Bearer <access_token>
# ---------------------------------------------------------------------------

def profile_route(authorization_header: str):
    token = authorization_header.replace("Bearer ", "")
    try:
        return get_profile(token=token)
    except (GuardError, UnauthorizedError):
        return {"error": "unauthorized"}, 401

def orders_route(authorization_header: str):
    token = authorization_header.replace("Bearer ", "")
    try:
        return get_orders(token=token)
    except (GuardError, UnauthorizedError):
        return {"error": "unauthorized"}, 401


# ---------------------------------------------------------------------------
# Token refresh — client sends the refresh token (from cookie)
# Server issues a new access token and rotates the refresh token
# ---------------------------------------------------------------------------

def refresh_route(refresh_token: str):
    try:
        payload = tm.decode_token(refresh_token)
    except TokenExpiredError:
        return {"error": "session expired, please log in again"}, 401
    except (GuardError, UnauthorizedError):
        return {"error": "invalid token"}, 401

    if payload["type"] != "refresh":
        return {"error": "wrong token type"}, 400

    # Invalidate old refresh token in your DB before issuing a new one
    db.revoke_refresh_token(refresh_token)

    new_access = tm.create_access_token(user_id=payload["user_id"])
    new_refresh = tm.create_refresh_token(user_id=payload["user_id"])

    db.store_refresh_token(new_refresh, user_id=payload["user_id"])

    # set new_refresh as httpOnly cookie in a real app
    return {"access_token": new_access}
```

---

## Password Hashing

gatevault uses bcrypt for password hashing. Passwords are one-way hashed — there is no way to reverse a hash back to the original password. If your database is ever compromised, attackers get hashes, not passwords.

### Hashing a password

```python
from gatevault import hash_password

hashed = hash_password("user_plain_password")
print(hashed)
# $2b$12$Kq8J3mNrandom...
```

Always hash at the point of registration and store the result. Never store or log the plain password.

```python
def register(username: str, plain_password: str):
    hashed = hash_password(plain_password)
    db.insert(username=username, hashed_password=hashed)
    return {"message": "account created"}
```

### Verifying a password

```python
from gatevault import verify_password

is_match = verify_password("user_plain_password", stored_hash)
# True or False
```

`verify_password` returns a boolean. It never raises on a wrong password — it just returns `False`. What you do with that result is your decision.

```python
from gatevault import verify_password, InvalidCredentialsError, UnauthorizedError

def authenticate(username: str, plain_password: str):
    user = db.get_user(username)
    if not user:
        raise InvalidCredentialsError("user not found")
    if not verify_password(plain_password, user.hashed_password):
        raise UnauthorizedError("wrong password")
    return user
```

### About bcrypt salting

You do not need to manage salts yourself. bcrypt generates a unique random salt for every hash and embeds it in the output string. Two calls to `hash_password` with the same password produce different hashes — both are valid.

```python
h1 = hash_password("same_password")
h2 = hash_password("same_password")

print(h1 == h2)                            # False — different salts
print(verify_password("same_password", h1)) # True
print(verify_password("same_password", h2)) # True
print(verify_password("wrong", h1))         # False
```

### Standalone usage

`hash_password` and `verify_password` have no dependency on the rest of gatevault. You can use them without setting up `TokenManager` or anything else:

```python
from gatevault import hash_password, verify_password

# registration
stored = hash_password("mypassword")

# login check
if verify_password("mypassword", stored):
    print("access granted")
else:
    print("access denied")
```

---

## Token Management

`TokenManager` handles all JWT creation and verification. It is the core of gatevault. Create one instance at startup and share it across your app.

### Setup

```python
import os
from gatevault import TokenManager

tm = TokenManager(
    secret_key=os.environ["AUTH_SECRET_KEY"],
    access_expiry_minutes=15,
    refresh_expiry_days=7
)
```

The `secret_key` is what signs your tokens. Anyone with this key can forge valid tokens — keep it in an environment variable, never in source code.

To generate a secure key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Creating tokens

```python
access_token = tm.create_access_token(user_id=42)
refresh_token = tm.create_refresh_token(user_id=42)

print(access_token)
# eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Access tokens are short-lived — meant to be sent with every authenticated request. Refresh tokens are long-lived — used only to get a new access token when the current one expires.

### Extra claims

You can embed additional data in the token payload using keyword arguments:

```python
# embed role and org at login time
access_token = tm.create_access_token(user_id=42, role="admin", org_id=7)

payload = tm.decode_token(access_token)
print(payload)
# {
#   "user_id": 42,
#   "exp": 1234567890,
#   "type": "access",
#   "role": "admin",
#   "org_id": 7
# }
```

This means your guards can make role-based decisions without hitting the database on every request:

```python
@gate.protected
def admin_dashboard(payload=None):
    if payload.get("role") != "admin":
        raise UnauthorizedError("admin access required")
    return get_admin_data()
```

### Decoding tokens

```python
payload = tm.decode_token(token)

user_id = payload["user_id"]
token_type = payload["type"]   # "access" or "refresh"
expiry = payload["exp"]        # unix timestamp
```

`decode_token` verifies the signature and checks expiry in one call. It raises specific exceptions on failure:

```python
from gatevault import TokenExpiredError, InvalidTokenError, TokenDecodeError

try:
    payload = tm.decode_token(token)
except TokenExpiredError:
    # token has passed its exp time — send client to refresh endpoint
    return {"error": "token expired"}, 401
except InvalidTokenError:
    # signature mismatch — token was tampered with
    return {"error": "invalid token"}, 401
except TokenDecodeError:
    # token string is malformed — can't be parsed
    return {"error": "malformed token"}, 400
```

### Access vs refresh — telling them apart

Every token carries a `type` claim. Check it when you need to enforce which kind of token is being used:

```python
payload = tm.decode_token(token)

if payload["type"] != "access":
    raise UnauthorizedError("expected an access token, got refresh")
```

This matters on your refresh endpoint — you only want refresh tokens there, not access tokens:

```python
def refresh_route(token: str):
    payload = tm.decode_token(token)
    if payload["type"] != "refresh":
        return {"error": "wrong token type"}, 400
    # proceed with issuing new tokens
```

### TokenManager is shared

`OAuthHandler` creates tokens using `TokenManager`. `GateVault` verifies tokens using the **same** `TokenManager`. They share the same secret key. Create one instance and pass it to both:

```python
tm = TokenManager(secret_key=os.environ["AUTH_SECRET_KEY"], access_expiry_minutes=15, refresh_expiry_days=7)

oauth = OAuthHandler(token_manager=tm, get_user=get_user)  # uses tm to create tokens
gate = GateVault(token_manager=tm)                          # uses tm to verify tokens
```

---

## Login Flow

`OAuthHandler` wires together user lookup, password verification, and token creation into one call. It follows the OAuth2 Resource Owner Password Credentials flow.

### Setup

```python
from gatevault import OAuthHandler

def get_user(username: str):
    # return a user object with `id` and `hashed_password` attributes
    # return None if the user doesn't exist
    return db.query(User).filter(User.email == username).first()

oauth = OAuthHandler(token_manager=tm, get_user=get_user)
```

Your `get_user` function must return an object with two attributes:

- `id` — the user's identifier, embedded in the token payload
- `hashed_password` — the bcrypt hash stored at registration

If your model uses different field names, add a property:

```python
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String)
    password_hash = Column(String)  # your field is called password_hash

    @property
    def hashed_password(self):
        return self.password_hash   # gatevault expects hashed_password
```

### What login does

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

1. Calls `get_user(username)` — raises `InvalidCredentialsError` if `None` is returned
2. Calls `verify_password(password, user.hashed_password)` — raises `UnauthorizedError` if it returns `False`
3. Calls `create_access_token` and `create_refresh_token` — raises `GuardError` if token creation fails

### What to do with the tokens

The access token goes back to the client in the response body. The refresh token should be set as an httpOnly cookie — it cannot be read by JavaScript:

```python
# pseudocode — adjust to your framework
def login_route(username, password, response):
    try:
        tokens = oauth.login(username, password)
    except (InvalidCredentialsError, UnauthorizedError):
        return {"error": "invalid credentials"}, 401

    # refresh token goes in a secure httpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=tokens["refresh_token"],
        httponly=True,
        secure=True,      # HTTPS only
        samesite="strict"
    )

    # access token goes in the response body — client stores in memory
    return {"access_token": tokens["access_token"]}
```

The client stores the access token in memory (a JS variable or equivalent). On every subsequent request, the client sends it in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

### Handling login errors

```python
from gatevault import InvalidCredentialsError, UnauthorizedError, GuardError

try:
    tokens = oauth.login(username, password)
except InvalidCredentialsError:
    # user not found
    return {"error": "invalid credentials"}, 401
except UnauthorizedError:
    # wrong password
    return {"error": "invalid credentials"}, 401
except GuardError:
    # token creation failed unexpectedly
    return {"error": "authentication failed"}, 500
```

> Return the same error message for both `InvalidCredentialsError` and `UnauthorizedError`. Distinguishing between them tells an attacker which usernames are valid.

---

## Protecting Routes

`GateVault` wraps any function with token verification. The wrapped function never executes if the token is missing, expired, or invalid. On success, the decoded payload is injected as the `payload` keyword argument.

### Setup

```python
from gatevault import GateVault

gate = GateVault(token_manager=tm)
```

### Basic usage

```python
@gate.protected
def get_profile(payload=None):
    user_id = payload["user_id"]
    return db.get_user(user_id)
```

The token is passed at call time:

```python
result = get_profile(token="eyJhbGci...")
```

In a real app, the token comes from the `Authorization` header — your framework extracts it and you pass it to the protected function:

```python
# Framework extracts the Authorization header
# Client sent: Authorization: Bearer eyJhbGci...

def profile_route(authorization_header: str):
    token = authorization_header.replace("Bearer ", "")
    try:
        return get_profile(token=token)
    except (GuardError, UnauthorizedError):
        return {"error": "unauthorized"}, 401
```

### Multiple protected routes

Decorate each function once and reuse:

```python
@gate.protected
def get_profile(payload=None):
    return db.get_user(payload["user_id"])

@gate.protected
def get_orders(payload=None):
    return db.get_orders(payload["user_id"])

@gate.protected
def get_delivery(order_id: int, payload=None):
    return db.get_delivery(order_id, payload["user_id"])

@gate.protected
def update_settings(settings: dict, payload=None):
    return db.update_settings(payload["user_id"], settings)
```

Each one is independently protected. The same access token works for all of them — the client sends the same `Authorization` header on every request, and each route passes it to its own protected function.

### Passing arguments alongside the token

Your function can accept any arguments alongside `payload`:

```python
@gate.protected
def get_post(post_id: int, payload=None):
    user_id = payload["user_id"]
    post = db.get_post(post_id)
    if post.owner_id != user_id:
        raise UnauthorizedError("not your post")
    return post

# pass token and other args together
result = get_post(post_id=7, token="eyJhbGci...")
```

### Role-based access using claims

Embed the role at token creation time:

```python
tokens = oauth.login(username, password)
# internally: tm.create_access_token(user_id=user.id, role=user.role)
```

Check it in your protected function:

```python
@gate.protected
def admin_only(payload=None):
    if payload.get("role") != "admin":
        raise UnauthorizedError("admin access required")
    return get_admin_data()

@gate.protected
def moderator_or_above(payload=None):
    if payload.get("role") not in ("admin", "moderator"):
        raise UnauthorizedError("insufficient permissions")
    return get_mod_tools()
```

### Handling guard errors

```python
from gatevault import GuardError, UnauthorizedError

try:
    result = get_profile(token=incoming_token)
except GuardError as e:
    # token missing, expired, or malformed
    return {"error": str(e)}, 401
except UnauthorizedError as e:
    # invalid signature or permission check failed
    return {"error": str(e)}, 401
```

---

## Exception Handling

All gatevault exceptions inherit from `GatevaultError`. Catch broadly or specifically depending on what you need.

```
GatevaultError
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
from gatevault import (
    GatevaultError,
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

### Catching broadly — one handler for everything

```python
try:
    tokens = oauth.login(username, password)
except GatevaultError as e:
    return {"error": str(e)}, 401
```

### Catching specifically — different response per failure

```python
try:
    payload = tm.decode_token(token)
except TokenExpiredError:
    # access token expired — tell client to use refresh token
    return {"error": "token expired", "code": "TOKEN_EXPIRED"}, 401
except InvalidTokenError:
    # signature mismatch — possible tampering
    return {"error": "invalid token", "code": "INVALID_TOKEN"}, 401
except TokenDecodeError:
    # token string is malformed — bad format
    return {"error": "malformed token", "code": "DECODE_ERROR"}, 400
```

### Catching by category — group related errors

```python
try:
    payload = tm.decode_token(token)
except TokenError:
    # catches all three: TokenExpiredError, InvalidTokenError, TokenDecodeError
    return {"error": "token error"}, 401
```

```python
try:
    tokens = oauth.login(username, password)
except GuardError:
    # catches InvalidCredentialsError and UnauthorizedError
    return {"error": "authentication failed"}, 401
```

### Real-world error handling pattern

```python
from gatevault import (
    GatevaultError, InvalidCredentialsError, UnauthorizedError,
    TokenExpiredError, TokenDecodeError, InvalidTokenError, GuardError
)

def handle_login(username: str, password: str):
    try:
        tokens = oauth.login(username, password)
        return {"access_token": tokens["access_token"]}, 200
    except (InvalidCredentialsError, UnauthorizedError):
        return {"error": "invalid credentials"}, 401
    except GuardError:
        return {"error": "authentication failed"}, 500

def handle_protected_request(token: str):
    try:
        return get_profile(token=token)
    except TokenExpiredError:
        return {"error": "token expired", "action": "refresh"}, 401
    except (InvalidTokenError, TokenDecodeError, GuardError):
        return {"error": "unauthorized"}, 401
    except UnauthorizedError:
        return {"error": "forbidden"}, 403
```

---

## Warnings

### `ShortKeyWarning`

Issued at `TokenManager` creation if the secret key is shorter than 32 bytes. HS256 requires at least 32 bytes per RFC 7518. This is a warning, not an error — your app will still run.

```python
import warnings
from gatevault import TokenManager, ShortKeyWarning

# This triggers a ShortKeyWarning
tm = TokenManager(secret_key="tooshort", access_expiry_minutes=15, refresh_expiry_days=7)
# UserWarning: Secret key is shorter than the recommended 32 bytes for HS256...
```

### Suppressing in tests

```python
import warnings
from gatevault import ShortKeyWarning

warnings.filterwarnings("ignore", category=ShortKeyWarning)

tm = TokenManager(secret_key="short", access_expiry_minutes=15, refresh_expiry_days=7)
# no warning
```

### Treating as an error in CI

```python
warnings.filterwarnings("error", category=ShortKeyWarning)

# Now this raises instead of warning — catches misconfigurations early
tm = TokenManager(secret_key="tooshort", access_expiry_minutes=15, refresh_expiry_days=7)
# ShortKeyWarning: Secret key is shorter than the recommended 32 bytes...
```

---

## Framework Integration

gatevault is framework-agnostic. Here is how it fits into FastAPI and Flask with proper token handling.

### FastAPI

The full flow — register, login, protected route, refresh:

```python
import os
from fastapi import FastAPI, Header, HTTPException, Response, Cookie
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from gatevault import TokenManager, OAuthHandler, GateVault, hash_password
from gatevault import (
    InvalidCredentialsError, UnauthorizedError,
    GuardError, TokenExpiredError, InvalidTokenError, TokenDecodeError
)

app = FastAPI()

tm = TokenManager(
    secret_key=os.environ["AUTH_SECRET_KEY"],
    access_expiry_minutes=15,
    refresh_expiry_days=7
)
gate = GateVault(token_manager=tm)
oauth = OAuthHandler(token_manager=tm, get_user=get_user_from_db)


class AuthRequest(BaseModel):
    username: str
    password: str


# Registration
@app.post("/register")
def register(body: AuthRequest):
    hashed = hash_password(body.password)
    db.create_user(username=body.username, hashed_password=hashed)
    return {"message": "registered"}


# Login — access token in body, refresh token in httpOnly cookie
@app.post("/login")
def login(body: AuthRequest, response: Response):
    try:
        tokens = oauth.login(body.username, body.password)
    except (InvalidCredentialsError, UnauthorizedError):
        raise HTTPException(status_code=401, detail="invalid credentials")

    response.set_cookie(
        key="refresh_token",
        value=tokens["refresh_token"],
        httponly=True,
        secure=True,
        samesite="strict"
    )
    return {"access_token": tokens["access_token"]}


# Protected functions — defined once
@gate.protected
def get_profile(payload=None):
    return db.get_user(payload["user_id"])

@gate.protected
def get_orders(payload=None):
    return db.get_orders(payload["user_id"])


# Routes — extract token from Authorization header, pass to protected function
@app.get("/profile")
def profile(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    try:
        return get_profile(token=token)
    except (GuardError, UnauthorizedError):
        raise HTTPException(status_code=401, detail="unauthorized")

@app.get("/orders")
def orders(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    try:
        return get_orders(token=token)
    except (GuardError, UnauthorizedError):
        raise HTTPException(status_code=401, detail="unauthorized")


# Refresh — refresh token comes from httpOnly cookie, not body
@app.post("/refresh")
def refresh(response: Response, refresh_token: str = Cookie(...)):
    try:
        payload = tm.decode_token(refresh_token)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="session expired")
    except (InvalidTokenError, TokenDecodeError):
        raise HTTPException(status_code=401, detail="invalid token")

    if payload["type"] != "refresh":
        raise HTTPException(status_code=400, detail="wrong token type")

    db.revoke_refresh_token(refresh_token)

    new_access = tm.create_access_token(user_id=payload["user_id"])
    new_refresh = tm.create_refresh_token(user_id=payload["user_id"])

    db.store_refresh_token(new_refresh, user_id=payload["user_id"])

    response.set_cookie(
        key="refresh_token",
        value=new_refresh,
        httponly=True,
        secure=True,
        samesite="strict"
    )
    return {"access_token": new_access}


# Logout — clear the cookie
@app.post("/logout")
def logout(response: Response, refresh_token: str = Cookie(None)):
    if refresh_token:
        db.revoke_refresh_token(refresh_token)
    response.delete_cookie("refresh_token")
    return {"message": "logged out"}
```

### Flask

```python
import os
from flask import Flask, request, jsonify, make_response
from gatevault import TokenManager, OAuthHandler, GateVault, hash_password
from gatevault import (
    InvalidCredentialsError, UnauthorizedError,
    GuardError, TokenExpiredError, InvalidTokenError, TokenDecodeError
)

app = Flask(__name__)

tm = TokenManager(
    secret_key=os.environ["AUTH_SECRET_KEY"],
    access_expiry_minutes=15,
    refresh_expiry_days=7
)
gate = GateVault(token_manager=tm)
oauth = OAuthHandler(token_manager=tm, get_user=get_user_from_db)


def get_token_from_header():
    auth = request.headers.get("Authorization", "")
    return auth.replace("Bearer ", "")


# Registration
@app.post("/register")
def register():
    data = request.json
    hashed = hash_password(data["password"])
    db.create_user(username=data["username"], hashed_password=hashed)
    return jsonify({"message": "registered"})


# Login — access token in body, refresh token in httpOnly cookie
@app.post("/login")
def login():
    data = request.json
    try:
        tokens = oauth.login(data["username"], data["password"])
    except (InvalidCredentialsError, UnauthorizedError):
        return jsonify({"error": "invalid credentials"}), 401

    response = make_response(jsonify({"access_token": tokens["access_token"]}))
    response.set_cookie(
        "refresh_token",
        tokens["refresh_token"],
        httponly=True,
        secure=True,
        samesite="Strict"
    )
    return response


# Protected functions — defined once
@gate.protected
def get_profile(payload=None):
    return db.get_user(payload["user_id"])

@gate.protected
def get_orders(payload=None):
    return db.get_orders(payload["user_id"])


# Routes — extract token from Authorization header
@app.get("/profile")
def profile():
    token = get_token_from_header()
    try:
        return jsonify(get_profile(token=token))
    except (GuardError, UnauthorizedError):
        return jsonify({"error": "unauthorized"}), 401

@app.get("/orders")
def orders():
    token = get_token_from_header()
    try:
        return jsonify(get_orders(token=token))
    except (GuardError, UnauthorizedError):
        return jsonify({"error": "unauthorized"}), 401


# Refresh — reads refresh token from httpOnly cookie
@app.post("/refresh")
def refresh():
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        return jsonify({"error": "no refresh token"}), 401

    try:
        payload = tm.decode_token(refresh_token)
    except TokenExpiredError:
        return jsonify({"error": "session expired"}), 401
    except (InvalidTokenError, TokenDecodeError):
        return jsonify({"error": "invalid token"}), 401

    if payload["type"] != "refresh":
        return jsonify({"error": "wrong token type"}), 400

    db.revoke_refresh_token(refresh_token)

    new_access = tm.create_access_token(user_id=payload["user_id"])
    new_refresh = tm.create_refresh_token(user_id=payload["user_id"])

    db.store_refresh_token(new_refresh, user_id=payload["user_id"])

    response = make_response(jsonify({"access_token": new_access}))
    response.set_cookie(
        "refresh_token",
        new_refresh,
        httponly=True,
        secure=True,
        samesite="Strict"
    )
    return response


# Logout
@app.post("/logout")
def logout():
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        db.revoke_refresh_token(refresh_token)
    response = make_response(jsonify({"message": "logged out"}))
    response.delete_cookie("refresh_token")
    return response
```

---

## Using gatevault in Parts

You do not have to use the whole package. Each part is independent.

### Just Hashing

No tokens, no guards — just bcrypt password management:

```python
from gatevault import hash_password, verify_password

# Registration
hashed = hash_password("user_password")
db.save_user(hashed_password=hashed)

# Login
user = db.get_user(username)
if verify_password("user_password", user.hashed_password):
    # authenticated — issue tokens however you like
    pass
else:
    raise Exception("wrong password")

# Password change
new_hash = hash_password("new_password")
db.update_password(user_id=user.id, hashed_password=new_hash)
```

### Just Tokens

Your own login flow, but JWT management handled by gatevault:

```python
from gatevault import TokenManager
from gatevault import TokenExpiredError, InvalidTokenError, TokenDecodeError

tm = TokenManager(
    secret_key="your-very-secure-secret-key-32-bytes",
    access_expiry_minutes=30,
    refresh_expiry_days=14
)

# issue tokens after your own auth check
access = tm.create_access_token(user_id=1)
refresh = tm.create_refresh_token(user_id=1)

# embed extra claims
access = tm.create_access_token(user_id=1, role="admin", plan="pro")

# decode and verify
try:
    payload = tm.decode_token(access)
    print(payload["user_id"])  # 1
    print(payload["role"])     # "admin"
    print(payload["type"])     # "access"
except TokenExpiredError:
    print("expired")
except InvalidTokenError:
    print("tampered")
except TokenDecodeError:
    print("malformed")
```

### Just Guards

You already have tokens, you just want decorator-based protection:

```python
from gatevault import TokenManager, GateVault
from gatevault import GuardError, UnauthorizedError

tm = TokenManager(
    secret_key="your-very-secure-secret-key-32-bytes",
    access_expiry_minutes=15,
    refresh_expiry_days=7
)
gate = GateVault(token_manager=tm)

@gate.protected
def get_dashboard(payload=None):
    return {"user_id": payload["user_id"], "role": payload.get("role")}

@gate.protected
def admin_panel(payload=None):
    if payload.get("role") != "admin":
        raise UnauthorizedError("admins only")
    return get_admin_data()

@gate.protected
def process_order(order_id: int, payload=None):
    return db.process(order_id, user_id=payload["user_id"])

# call with token from wherever you got it
try:
    result = get_dashboard(token=incoming_token)
except GuardError:
    return {"error": "unauthorized"}, 401
except UnauthorizedError:
    return {"error": "forbidden"}, 403
```

---

## Token Refresh & Rotation

gatevault creates tokens on demand but does not manage storage or invalidation — that lives in your application.

### Why you need a refresh token store

JWTs cannot be invalidated once issued. Without a store, a stolen refresh token is valid until it expires — potentially days. With a store, you can:

- Revoke tokens on logout
- Detect token reuse (a sign of theft)
- Force re-login on password change or suspicious activity

### Full rotation pattern

```python
from gatevault import TokenExpiredError, InvalidTokenError, TokenDecodeError

def rotate_tokens(refresh_token: str):
    # 1. Verify the refresh token
    try:
        payload = tm.decode_token(refresh_token)
    except TokenExpiredError:
        return {"error": "session expired, please log in again"}, 401
    except (InvalidTokenError, TokenDecodeError):
        return {"error": "invalid token"}, 401

    # 2. Check it's actually a refresh token
    if payload["type"] != "refresh":
        return {"error": "wrong token type"}, 400

    # 3. Check it hasn't already been used (reuse detection)
    if not db.is_refresh_token_valid(refresh_token):
        # Token was already rotated — possible theft
        # Revoke all tokens for this user and force re-login
        db.revoke_all_tokens_for_user(payload["user_id"])
        return {"error": "token reuse detected, please log in again"}, 401

    # 4. Revoke the old refresh token
    db.revoke_refresh_token(refresh_token)

    # 5. Issue new pair
    new_access = tm.create_access_token(user_id=payload["user_id"])
    new_refresh = tm.create_refresh_token(user_id=payload["user_id"])

    # 6. Store the new refresh token
    db.store_refresh_token(new_refresh, user_id=payload["user_id"])

    return {
        "access_token": new_access,
        "new_refresh_token": new_refresh
    }
```

### Minimal refresh (no reuse detection)

If you don't need reuse detection, here is the minimal version:

```python
def rotate_tokens(refresh_token: str):
    try:
        payload = tm.decode_token(refresh_token)
    except TokenExpiredError:
        return {"error": "session expired"}, 401
    except (InvalidTokenError, TokenDecodeError):
        return {"error": "invalid token"}, 401

    if payload["type"] != "refresh":
        return {"error": "wrong token type"}, 400

    new_access = tm.create_access_token(user_id=payload["user_id"])
    new_refresh = tm.create_refresh_token(user_id=payload["user_id"])

    return {"access_token": new_access, "refresh_token": new_refresh}
```

---

## Security Guide

### Secret key

- Use at least 32 bytes — gatevault warns you if you don't
- Generate with: `python -c "import secrets; print(secrets.token_hex(32))"`
- Store in an environment variable — never hardcode
- Rotating invalidates all existing tokens immediately — only do it when necessary (breach, employee offboarding)

### Token storage on the client

| Token | Where to store | Why |
|---|---|---|
| Access token | Memory (JS variable) | Short-lived, not persisted, wiped on tab close |
| Refresh token | httpOnly cookie | Can't be read by JavaScript — XSS safe |

Never store tokens in `localStorage` — it is accessible to any JavaScript on the page, including injected scripts.

### What not to put in the payload

The JWT payload is base64 encoded, not encrypted. Anyone with the token string can decode and read it. Keep it to identifiers and non-sensitive metadata:

```python
# Fine
tm.create_access_token(user_id=42, role="admin", org_id=7)

# Never do this
tm.create_access_token(user_id=42, email="john@example.com", password_hash="$2b$...")
```

### Refresh token revocation

Tokens cannot be invalidated once issued. For true revocation (logout, password change, suspicious activity), maintain a table of valid refresh tokens in your database:

```sql
CREATE TABLE refresh_tokens (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL
);
```

On every refresh request, check the token exists in this table before issuing a new pair. On logout or password change, delete the row.

### Login enumeration

Return the same error for "user not found" and "wrong password". Distinguishing them tells an attacker which usernames exist:

```python
# Good
except (InvalidCredentialsError, UnauthorizedError):
    return {"error": "invalid credentials"}, 401

# Bad — tells attacker the username is valid
except InvalidCredentialsError:
    return {"error": "user not found"}, 404
except UnauthorizedError:
    return {"error": "wrong password"}, 401
```

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
| `decode_token(token)` | `dict` | Verifies signature and expiry. Returns payload dict. Raises on failure. |

---

### `OAuthHandler(token_manager, get_user)`

| Parameter | Type | Description |
|---|---|---|
| `token_manager` | `TokenManager` | Configured TokenManager instance. |
| `get_user` | `Callable[[str], Any \| None]` | Lookup function. Must return object with `id` and `hashed_password`, or `None`. |

| Method | Returns | Description |
|---|---|---|
| `login(username, password)` | `dict` | Authenticates user. Returns `{"access_token", "refresh_token", "token_type"}`. |

---

### `GateVault(token_manager)`

| Parameter | Type | Description |
|---|---|---|
| `token_manager` | `TokenManager` | Configured TokenManager instance. |

| Method | Returns | Description |
|---|---|---|
| `protected(f)` | `Callable` | Decorator. Verifies token, injects decoded payload as `payload` kwarg. |

---

### `hash_password(plain) -> str`

| Parameter | Type | Description |
|---|---|---|
| `plain` | `str` | Plain text password. Encoding is handled internally. |

Returns bcrypt hash string. Raises `HashingError` on unexpected failure.

---

### `verify_password(plain, hashed) -> bool`

| Parameter | Type | Description |
|---|---|---|
| `plain` | `str` | Plain text password to check. |
| `hashed` | `str` | Stored bcrypt hash. |

Returns `True` if match, `False` otherwise. Never raises on wrong password.

---

## Design Decisions

**Framework-agnostic**

Tying gatevault to FastAPI or Flask would limit who can use it. Auth logic — hashing, signing, verifying — has nothing to do with HTTP. Pure Python means it works anywhere.

**Class-based `TokenManager`**

The secret key and expiry settings are configuration — they belong on an instance, not passed into every function call. Configure once at startup, use everywhere without threading arguments through every call.

**Shared `TokenManager` across `OAuthHandler` and `GateVault`**

`OAuthHandler` creates tokens. `GateVault` verifies them. They don't communicate directly — the shared `TokenManager` instance is the trust anchor. Same secret key in, same secret key out.

**Payload injected as a keyword argument**

`payload=payload` is explicit. The decorated function always knows where its auth data comes from. Positional injection would silently break functions whose arguments don't match the expected order.

**Wrapping third-party exceptions**

`PyJWT` and `bcrypt` exceptions never surface through the gatevault API. Consumers only need to know gatevault exceptions. If an underlying library changes exception names in a future version, only gatevault updates.

**`verify_password` returns bool, not raises**

A wrong password is an expected outcome, not an exceptional one. The caller decides whether to raise, log, increment a failed attempt counter, or something else entirely.

**`OAuthHandler.login` returns both tokens**

The server decides how to deliver each token to the client — access token in the body, refresh token in an httpOnly cookie. Returning both from `login` gives the framework integration layer that flexibility.

---

## Known Limitations

- Refresh token invalidation is not built in — you need a database or cache to track and revoke issued refresh tokens
- Only HS256 (symmetric signing) is supported — RS256 (asymmetric keypair) is not yet available
- `GateVault.protected` expects `token` as a keyword argument — you may need a thin adapter in frameworks with unusual request injection patterns
- No built-in rate limiting on login attempts — implement at the application or infrastructure level
- No async support — all methods are synchronous. Async wrappers are on the roadmap

---

## Future Improvements

- RS256 support for asymmetric key signing
- Built-in token blocklist interface for revocation
- Async-compatible versions of all methods (`async def`)
- Role-based access control helpers on `GateVault`
- FastAPI and Flask integration packages as optional extras

---

## Contributing

Contributions are welcome. Open an issue first to discuss what you want to change, especially for anything touching the security-sensitive parts.

```bash
git clone https://github.com/RichardOyelowo/gatevault
cd gatevault
pip install -e .
pip install pytest
pytest tests/ -v
```

---

## License

Apache 2.0 — see [LICENSE](./LICENSE) for details.

---

*Built by Richard for the love of development.*