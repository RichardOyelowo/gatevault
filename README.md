# <img src="images/brown_logo.svg">

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
  - [Sync Login](#sync-login)
  - [Async Login](#async-login)
- [Protecting Routes](#protecting-routes)
- [Exception Handling](#exception-handling)
- [Warnings](#warnings)
- [Framework Integration](#framework-integration)
  - [FastAPI (Async)](#fastapi-async)
  - [FastAPI (Sync)](#fastapi-sync)
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

Here is what a complete auth setup looks like end to end — registration, login, token storage, protected routes, and token refresh. This example uses `async_login` for an async SQLAlchemy setup. If you are using a synchronous database, replace `async_login` with `login` and remove the `async`/`await` keywords from the login route.

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


# ---------------------------------------------------------------------------
# get_user — async version for use with async_login
# ---------------------------------------------------------------------------

async def get_user(username: str):
    result = await db.execute(select(User).where(User.email == username))
    return result.scalar_one_or_none()

oauth = OAuthHandler(token_manager=tm, get_user=get_user)


# ---------------------------------------------------------------------------
# Registration — hash and store the password
# ---------------------------------------------------------------------------

async def register(username: str, plain_password: str):
    hashed = hash_password(plain_password)
    await db.create_user(username=username, hashed_password=hashed)
    return {"message": "registered"}


# ---------------------------------------------------------------------------
# Login — uses async_login since get_user is async
# Returns access token in body, refresh token goes in httpOnly cookie
# ---------------------------------------------------------------------------

async def login(username: str, password: str):
    try:
        tokens = await oauth.async_login(username, password)
    except (InvalidCredentialsError, UnauthorizedError):
        return {"error": "invalid credentials"}, 401

    # set refresh token as httpOnly cookie in your framework
    # return only the access token in the response body
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


# ---------------------------------------------------------------------------
# Token refresh — client sends the refresh token (from cookie)
# ---------------------------------------------------------------------------

async def refresh_route(refresh_token: str):
    try:
        payload = tm.decode_token(refresh_token)
    except TokenExpiredError:
        return {"error": "session expired, please log in again"}, 401
    except (GuardError, UnauthorizedError):
        return {"error": "invalid token"}, 401

    if payload["type"] != "refresh":
        return {"error": "wrong token type"}, 400

    await db.revoke_refresh_token(refresh_token)

    new_access = tm.create_access_token(user_id=payload["user_id"])
    new_refresh = tm.create_refresh_token(user_id=payload["user_id"])

    await db.store_refresh_token(new_refresh, user_id=payload["user_id"])

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

print(h1 == h2)                             # False — different salts
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

It supports both **synchronous** and **asynchronous** user lookup — use `login` for sync databases (SQLAlchemy sync, raw psycopg2) and `async_login` for async databases (async SQLAlchemy, asyncpg, Tortoise ORM).

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

---

### Sync Login

Use `login` when your `get_user` function is a regular synchronous function:

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

---

### Async Login

Use `async_login` when your `get_user` function is defined as `async def` — typically when using async SQLAlchemy, asyncpg, or any other async ORM. It is identical to `login` but awaits the `get_user` call.

```python
async def get_user(username: str):
    result = await db.execute(select(User).where(User.email == username))
    return result.scalar_one_or_none()

oauth = OAuthHandler(token_manager=tm, get_user=get_user)

# must be called with await inside an async context
tokens = await oauth.async_login("john@example.com", "their_password")

print(tokens)
# {
#     "access_token": "eyJhbGci...",
#     "refresh_token": "eyJhbGci...",
#     "token_type": "bearer"
# }
```

`async_login` does the same three steps as `login` — the only difference is that `get_user` is awaited. The rest of the flow (password verification, token creation) remains synchronous.

> If you call `async_login` with a synchronous `get_user`, it will raise a `TypeError` because you cannot `await` a non-coroutine. Conversely, calling `login` with an async `get_user` will return a coroutine object instead of a user — always match the method to your `get_user` type.

---

### What to do with the tokens

The access token goes back to the client in the response body. The refresh token should be set as an httpOnly cookie — it cannot be read by JavaScript:

```python
# pseudocode — adjust to your framework
async def login_route(username, password, response):
    try:
        tokens = await oauth.async_login(username, password)
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

The server's job ends there. The client receives the access token in the response body and is responsible for storing it in memory (a JS variable, not `localStorage`). On every subsequent request, the client reads it from memory and puts it in the `Authorization` header manually:

```
Authorization: Bearer <access_token>
```

The refresh token is different — the browser stores and sends httpOnly cookies automatically, so the client never has to handle it directly.

Client-side example:

```javascript
// After login — store access token in memory
const { access_token } = await fetch("/login", {
    method: "POST",
    body: JSON.stringify({ username, password })
}).then(r => r.json())

// On every protected request — send it in the Authorization header
const profile = await fetch("/profile", {
    headers: { "Authorization": `Bearer ${access_token}` }
}).then(r => r.json())

// When access token expires — browser sends refresh cookie automatically
const refreshed = await fetch("/refresh", {
    method: "POST",
    credentials: "include"  // sends the httpOnly cookie
}).then(r => r.json())

// Store the new access token
const new_access_token = refreshed.access_token
```

### Handling login errors

```python
from gatevault import InvalidCredentialsError, UnauthorizedError, GuardError

try:
    tokens = await oauth.async_login(username, password)
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

The token is passed at call time via `token=`. In a real app, the token is not something you have directly in your server code — the client sends it in the `Authorization` header, your framework gives you access to that header, and you extract the token from it and pass it to the protected function:

```python
def profile_route(authorization_header: str):
    token = authorization_header.replace("Bearer ", "")
    try:
        return get_profile(token=token)
    except (GuardError, UnauthorizedError):
        return {"error": "unauthorized"}, 401
```

### Multiple protected routes

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

### Passing arguments alongside the token

```python
@gate.protected
def get_post(post_id: int, payload=None):
    user_id = payload["user_id"]
    post = db.get_post(post_id)
    if post.owner_id != user_id:
        raise UnauthorizedError("not your post")
    return post

result = get_post(post_id=7, token="eyJhbGci...")
```

### Role-based access using claims

Embed the role at token creation time and check it in your protected function:

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
    return {"error": str(e)}, 401
except UnauthorizedError as e:
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

### Catching broadly

```python
try:
    tokens = await oauth.async_login(username, password)
except GatevaultError as e:
    return {"error": str(e)}, 401
```

### Catching specifically

```python
try:
    payload = tm.decode_token(token)
except TokenExpiredError:
    return {"error": "token expired", "code": "TOKEN_EXPIRED"}, 401
except InvalidTokenError:
    return {"error": "invalid token", "code": "INVALID_TOKEN"}, 401
except TokenDecodeError:
    return {"error": "malformed token", "code": "DECODE_ERROR"}, 400
```

### Catching by category

```python
try:
    payload = tm.decode_token(token)
except TokenError:
    # catches TokenExpiredError, InvalidTokenError, TokenDecodeError
    return {"error": "token error"}, 401
```

```python
try:
    tokens = await oauth.async_login(username, password)
except GuardError:
    # catches InvalidCredentialsError and UnauthorizedError
    return {"error": "authentication failed"}, 401
```

---

## Warnings

### `ShortKeyWarning`

Issued at `TokenManager` creation if the secret key is shorter than 32 bytes. HS256 requires at least 32 bytes per RFC 7518.

```python
import warnings
from gatevault import TokenManager, ShortKeyWarning

warnings.filterwarnings("ignore", category=ShortKeyWarning)
tm = TokenManager(secret_key="short", access_expiry_minutes=15, refresh_expiry_days=7)
```

### Treating as an error in CI

```python
warnings.filterwarnings("error", category=ShortKeyWarning)
```

---

## Framework Integration

### FastAPI (Async)

The recommended setup for FastAPI — uses `async_login` with async SQLAlchemy:

```python
import os
from fastapi import FastAPI, Header, HTTPException, Response, Cookie, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# async get_user for use with async_login
async def get_user(username: str, db: AsyncSession):
    result = await db.execute(select(User).where(User.email == username))
    return result.scalar_one_or_none()


# Registration
@app.post("/register")
async def register(body: UserCreate, db: AsyncSession = Depends(get_db)):
    hashed = hash_password(body.password)
    new_user = User(email=body.email, hashed_password=hashed)
    db.add(new_user)
    await db.commit()
    return {"message": "registered"}


# Login — async_login for async DB lookup
@app.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    response: Response = None,
    db: AsyncSession = Depends(get_db)
):
    async def _get_user(username: str):
        return await get_user(username, db)

    oauth = OAuthHandler(token_manager=tm, get_user=_get_user)

    try:
        tokens = await oauth.async_login(form_data.username, form_data.password)
    except (InvalidCredentialsError, UnauthorizedError):
        raise HTTPException(status_code=401, detail="invalid credentials")

    response.set_cookie(
        key="refresh_token",
        value=tokens["refresh_token"],
        httponly=True,
        secure=True,
        samesite="strict"
    )
    return {"access_token": tokens["access_token"], "token_type": "bearer"}


# Token refresh
@app.post("/refresh")
async def refresh(response: Response, refresh_token: str = Cookie(...)):
    try:
        payload = tm.decode_token(refresh_token)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="session expired")
    except (InvalidTokenError, TokenDecodeError):
        raise HTTPException(status_code=401, detail="invalid token")

    if payload["type"] != "refresh":
        raise HTTPException(status_code=400, detail="wrong token type")

    new_access = tm.create_access_token(user_id=payload["user_id"])
    new_refresh = tm.create_refresh_token(user_id=payload["user_id"])

    response.set_cookie(
        key="refresh_token",
        value=new_refresh,
        httponly=True,
        secure=True,
        samesite="strict"
    )
    return {"access_token": new_access}


# Logout
@app.post("/logout")
def logout(response: Response, refresh_token: str = Cookie(None)):
    response.delete_cookie("refresh_token")
    return {"message": "logged out"}
```

---

### FastAPI (Sync)

If you are using a synchronous database driver, use `login` instead:

```python
oauth = OAuthHandler(token_manager=tm, get_user=get_user_from_db)

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), response: Response = None):
    try:
        tokens = oauth.login(form_data.username, form_data.password)
    except (InvalidCredentialsError, UnauthorizedError):
        raise HTTPException(status_code=401, detail="invalid credentials")

    response.set_cookie(
        key="refresh_token",
        value=tokens["refresh_token"],
        httponly=True,
        secure=True,
        samesite="strict"
    )
    return {"access_token": tokens["access_token"], "token_type": "bearer"}
```

---

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
```

---

## Using gatevault in Parts

### Just Hashing

```python
from gatevault import hash_password, verify_password

stored = hash_password("user_password")

if verify_password("user_password", stored):
    print("access granted")
else:
    print("access denied")
```

### Just Tokens

```python
from gatevault import TokenManager

tm = TokenManager(
    secret_key="your-very-secure-secret-key-32-bytes",
    access_expiry_minutes=30,
    refresh_expiry_days=14
)

access = tm.create_access_token(user_id=1, role="admin")
refresh = tm.create_refresh_token(user_id=1)

payload = tm.decode_token(access)
print(payload["user_id"])  # 1
print(payload["role"])     # "admin"
print(payload["type"])     # "access"
```

### Just Guards

```python
from gatevault import TokenManager, GateVault

tm = TokenManager(secret_key="...", access_expiry_minutes=15, refresh_expiry_days=7)
gate = GateVault(token_manager=tm)

@gate.protected
def get_dashboard(payload=None):
    return {"user_id": payload["user_id"]}

try:
    result = get_dashboard(token=incoming_token)
except GuardError:
    return {"error": "unauthorized"}, 401
```

---

## Token Refresh & Rotation

gatevault creates tokens on demand but does not manage storage or invalidation — that lives in your application.

### Full rotation pattern

```python
from gatevault import TokenExpiredError, InvalidTokenError, TokenDecodeError

def rotate_tokens(refresh_token: str):
    try:
        payload = tm.decode_token(refresh_token)
    except TokenExpiredError:
        return {"error": "session expired, please log in again"}, 401
    except (InvalidTokenError, TokenDecodeError):
        return {"error": "invalid token"}, 401

    if payload["type"] != "refresh":
        return {"error": "wrong token type"}, 400

    if not db.is_refresh_token_valid(refresh_token):
        db.revoke_all_tokens_for_user(payload["user_id"])
        return {"error": "token reuse detected, please log in again"}, 401

    db.revoke_refresh_token(refresh_token)

    new_access = tm.create_access_token(user_id=payload["user_id"])
    new_refresh = tm.create_refresh_token(user_id=payload["user_id"])

    db.store_refresh_token(new_refresh, user_id=payload["user_id"])

    return {"access_token": new_access, "new_refresh_token": new_refresh}
```

---

## Security Guide

### Secret key

- Use at least 32 bytes — gatevault warns you if you don't
- Generate with: `python -c "import secrets; print(secrets.token_hex(32))"`
- Store in an environment variable — never hardcode
- Rotating invalidates all existing tokens immediately

### Token storage on the client

| Token | Where to store | Why |
|---|---|---|
| Access token | Memory (JS variable) | Short-lived, not persisted, wiped on tab close |
| Refresh token | httpOnly cookie | Can't be read by JavaScript — XSS safe |

Never store tokens in `localStorage`.

### What not to put in the payload

The JWT payload is base64 encoded, not encrypted. Keep it to identifiers and non-sensitive metadata:

```python
# Fine
tm.create_access_token(user_id=42, role="admin", org_id=7)

# Never do this
tm.create_access_token(user_id=42, email="john@example.com", password_hash="$2b$...")
```

### Login enumeration

Return the same error for "user not found" and "wrong password":

```python
# Good
except (InvalidCredentialsError, UnauthorizedError):
    return {"error": "invalid credentials"}, 401

# Bad — tells attacker the username is valid
except InvalidCredentialsError:
    return {"error": "user not found"}, 404
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
| `get_user` | `Callable[[str], Any \| None]` | Lookup function. Sync or async. Must return object with `id` and `hashed_password`, or `None`. |

| Method | Returns | Description |
|---|---|---|
| `login(username, password)` | `dict` | Authenticates user synchronously. Returns `{"access_token", "refresh_token", "token_type"}`. |
| `async_login(username, password)` | `Coroutine[dict]` | Authenticates user asynchronously — use when `get_user` is `async def`. Must be called with `await`. |

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

Returns bcrypt hash string. Raises `HashingError` on unexpected failure.

---

### `verify_password(plain, hashed) -> bool`

Returns `True` if match, `False` otherwise. Never raises on wrong password.

---

## Design Decisions

**Framework-agnostic**

Tying gatevault to FastAPI or Flask would limit who can use it. Auth logic — hashing, signing, verifying — has nothing to do with HTTP. Pure Python means it works anywhere.

**Both sync and async login**

`async_login` was added to support async ORMs like async SQLAlchemy without requiring a separate library or workaround. The two methods are intentionally separate — calling the wrong one for your `get_user` type fails loudly rather than silently returning a coroutine instead of a user.

**Class-based `TokenManager`**

The secret key and expiry settings are configuration — they belong on an instance, not passed into every function call. Configure once at startup, use everywhere.

**Shared `TokenManager` across `OAuthHandler` and `GateVault`**

`OAuthHandler` creates tokens. `GateVault` verifies them. The shared `TokenManager` instance is the trust anchor — same secret key in, same secret key out.

**Payload injected as a keyword argument**

`payload=payload` is explicit. The decorated function always knows where its auth data comes from. Positional injection would silently break functions whose arguments don't match the expected order.

**Wrapping third-party exceptions**

`PyJWT` and `bcrypt` exceptions never surface through the gatevault API. Consumers only need to know gatevault exceptions.

**`verify_password` returns bool, not raises**

A wrong password is an expected outcome, not an exceptional one. The caller decides whether to raise, log, or increment a failed attempt counter.

---

## Known Limitations

- Refresh token invalidation is not built in — you need a database or cache to track and revoke issued refresh tokens
- Only HS256 (symmetric signing) is supported — RS256 is not yet available
- `GateVault.protected` is synchronous only — async route protection is on the roadmap
- No built-in rate limiting on login attempts — implement at the application or infrastructure level

---

## Future Improvements

- RS256 support for asymmetric key signing
- Built-in token blocklist interface for revocation
- Async `GateVault.protected` decorator for async route functions
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
**Built by Richard for the love of development.**
