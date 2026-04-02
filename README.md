# <img src="images/brown_logo.png">

<p align="center">
  <a href="https://pypi.org/project/richard-gatevault/"><img src="https://img.shields.io/pypi/v/richard-gatevault?color=8B4513&label=pypi&style=flat-square"></a>
  <a href="https://pypi.org/project/richard-gatevault/"><img src="https://img.shields.io/pypi/pyversions/richard-gatevault?color=3776AB&style=flat-square"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-orange?style=flat-square"></a>
  <a href="https://github.com/RichardOyelowo/gatevault/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/RichardOyelowo/gatevault/ci.yml?label=CI&style=flat-square"></a>
  <a href="https://linkedin.com/in/richard-oyelowo"><img src="https://img.shields.io/badge/LinkedIn-Richard%20Oyelowo-0077B5?logo=linkedin&style=flat-square"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white">
  <img src="https://img.shields.io/badge/Flask-000000?style=flat-square&logo=flask&logoColor=white">
  <img src="https://img.shields.io/badge/Django-092E20?style=flat-square&logo=django&logoColor=white">
  <img src="https://img.shields.io/badge/async%2Fawait-supported-4B8BBE?style=flat-square&logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/SQLAlchemy-async-red?style=flat-square">
</p>

---

A Python auth library that handles JWT token management, password hashing, OAuth2 login flow, and route protection — with full sync and async support — so you don't have to wire it together yourself.

Most auth libraries do one thing. `PyJWT` gives you JWT encoding. `bcrypt` gives you password hashing. You still have to write the login flow, build the guards, handle the exceptions, and repeat that boilerplate across every project. gatevault wraps all of it into one coherent package with a clean API you can drop into any Python project regardless of framework — whether you're using FastAPI with async SQLAlchemy, Flask with a sync ORM, or Django with its built-in ORM.

```bash
pip install richard-gatevault
```

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [The Full Picture](#the-full-picture)
- [Password Hashing](#password-hashing)
- [Token Management](#token-management)
- [Login Flow](#login-flow)
  - [Sync Login](#sync-login)
  - [Async Login](#async-login)
- [Protecting Routes](#protecting-routes)
  - [Sync Protection](#sync-protection)
  - [Async Protection](#async-protection)
- [Exception Handling](#exception-handling)
- [Warnings](#warnings)
- [Framework Integration](#framework-integration)
  - [FastAPI (Async)](#fastapi-async)
  - [FastAPI (Sync)](#fastapi-sync)
  - [Flask](#flask)
  - [Django](#django)
    - [Django REST Framework](#django-rest-framework)
    - [Async Django Views](#async-django-views-django-41)
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

Requires Python 3.9+. Dependencies `PyJWT` and `bcrypt` are installed automatically — no extra setup needed.

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

## Quick Start

The fastest path from zero to a working auth setup. This assumes a sync database — swap `login` for `async_login` and add `async def` if you're using an async ORM.

```python
import os
from gatevault import TokenManager, OAuthHandler, GateVault, hash_password
from gatevault import InvalidCredentialsError, UnauthorizedError, GuardError

# 1. Initialize once at startup
tm = TokenManager(
    secret_key=os.environ["AUTH_SECRET_KEY"],
    access_expiry_minutes=15,
    refresh_expiry_days=7
)
gate = GateVault(token_manager=tm)
oauth = OAuthHandler(token_manager=tm, get_user=lambda u: db.get_user(u))

# 2. Hash passwords at registration
hashed = hash_password(plain_password)
db.save_user(email=email, hashed_password=hashed)

# 3. Login returns tokens
tokens = oauth.login(email, password)
# → {"access_token": "eyJ...", "refresh_token": "eyJ...", "token_type": "bearer"}

# 4. Protect any function with a decorator
@gate.protected
def get_profile(payload=None):
    return db.get_user(payload["user_id"])

# Works on async functions too
@gate.protected
async def get_profile_async(payload=None):
    return await db.get_user(payload["user_id"])

# 5. Call the protected function with the token
result = get_profile(token=access_token)
result = await get_profile_async(token=access_token)
```

### Choosing the right method

| Situation | Use |
|---|---|
| Sync database (Django ORM, SQLAlchemy sync) | `oauth.login(...)` |
| Async database (async SQLAlchemy, asyncpg) | `await oauth.async_login(...)` |
| Protecting a regular function | `@gate.protected` + `def` |
| Protecting an async route/function | `@gate.protected` + `async def` |

---

## The Full Picture

Here is what a complete auth setup looks like end to end — registration, login, token storage, protected routes, and token refresh.

This example uses `async_login` and `async def` protected routes for an async SQLAlchemy setup. If you are using a synchronous database, replace `async_login` with `login`, `async def` protected functions with regular `def`, and remove the `async`/`await` keywords from the login route.

```python
import os
from gatevault import (
    TokenManager, OAuthHandler, GateVault,
    hash_password,
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
# Registration — hash and store the password, never store plain text
# ---------------------------------------------------------------------------

async def register(username: str, plain_password: str):
    hashed = hash_password(plain_password)
    await db.create_user(username=username, hashed_password=hashed)
    return {"message": "registered"}


# ---------------------------------------------------------------------------
# Login — uses async_login since get_user is async
# Access token goes in the response body.
# Refresh token goes in an httpOnly cookie — never in the body.
# ---------------------------------------------------------------------------

async def login(username: str, password: str, response):
    try:
        tokens = await oauth.async_login(username, password)
    except (InvalidCredentialsError, UnauthorizedError):
        return {"error": "invalid credentials"}, 401

    response.set_cookie(
        key="refresh_token",
        value=tokens["refresh_token"],
        httponly=True,
        secure=True,
        samesite="strict"
    )
    return {"access_token": tokens["access_token"]}


# ---------------------------------------------------------------------------
# Protected functions — gatevault.protected works on both sync and async
# ---------------------------------------------------------------------------

@gate.protected
async def get_profile(payload=None):
    user_id = payload["user_id"]
    return await db.get_user(user_id)

@gate.protected
def get_orders(payload=None):
    user_id = payload["user_id"]
    return db.get_orders(user_id)


# ---------------------------------------------------------------------------
# Token refresh — client sends the refresh token via httpOnly cookie
# Server issues a new access token
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

stored = hash_password("mypassword")

if verify_password("mypassword", stored):
    print("access granted")
else:
    print("access denied")
```

---

## Token Management

`TokenManager` handles all JWT creation and verification. It is the core of gatevault — `OAuthHandler` uses it to create tokens and `GateVault` uses it to verify them. Create one instance at startup and share it across your app.

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
```

Access tokens are short-lived (minutes) — sent with every authenticated request. Refresh tokens are long-lived (days) — used only to obtain a new access token when the current one expires.

### Extra claims

You can embed additional data in the token payload using keyword arguments. This is useful for role-based access control — you can check the role from the token itself without a database lookup on every request:

```python
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
    # token string is malformed — can't be parsed at all
    return {"error": "malformed token"}, 400
```

### Access vs refresh — telling them apart

Every token carries a `type` claim. Always check it on your refresh endpoint — you only want refresh tokens there:

```python
payload = tm.decode_token(token)

if payload["type"] != "refresh":
    return {"error": "wrong token type"}, 400
```

### TokenManager is shared

`OAuthHandler` creates tokens. `GateVault` verifies them. They don't communicate directly — the shared `TokenManager` instance is the trust anchor. Same secret key in, same secret key out.

```python
tm = TokenManager(secret_key=os.environ["AUTH_SECRET_KEY"], access_expiry_minutes=15, refresh_expiry_days=7)

oauth = OAuthHandler(token_manager=tm, get_user=get_user)  # uses tm to create tokens
gate = GateVault(token_manager=tm)                          # uses tm to verify tokens
```

---

## Login Flow

`OAuthHandler` wires together user lookup, password verification, and token creation into one call. It follows the OAuth2 Resource Owner Password Credentials flow.

It supports both **synchronous** and **asynchronous** user lookup — use `login` for sync databases (SQLAlchemy sync, Django ORM, raw psycopg2) and `async_login` for async databases (async SQLAlchemy, asyncpg, Tortoise ORM).

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
    password_hash = Column(String)

    @property
    def hashed_password(self):
        return self.password_hash  # gatevault expects hashed_password
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

Use `async_login` when your `get_user` function is defined as `async def` — typically when using async SQLAlchemy, asyncpg, or any async ORM. It performs the exact same three steps as `login`, but awaits the `get_user` call.

```python
async def get_user(username: str):
    result = await db.execute(select(User).where(User.email == username))
    return result.scalar_one_or_none()

oauth = OAuthHandler(token_manager=tm, get_user=get_user)

# must be awaited inside an async context
tokens = await oauth.async_login("john@example.com", "their_password")

print(tokens)
# {
#     "access_token": "eyJhbGci...",
#     "refresh_token": "eyJhbGci...",
#     "token_type": "bearer"
# }
```

> **Important:** Always match the method to your `get_user` type. Calling `async_login` with a sync `get_user` raises `TypeError` because you cannot `await` a plain value. Calling `login` with an async `get_user` returns a coroutine object instead of a user — authentication will silently fail. When in doubt, check whether your `get_user` is `async def`.

---

### What to do with the tokens

The access token goes back to the client in the response body. The refresh token should be set as an httpOnly cookie — it is invisible to JavaScript and therefore safe from XSS attacks:

```python
async def login_route(username, password, response):
    try:
        tokens = await oauth.async_login(username, password)
    except (InvalidCredentialsError, UnauthorizedError):
        return {"error": "invalid credentials"}, 401

    response.set_cookie(
        key="refresh_token",
        value=tokens["refresh_token"],
        httponly=True,
        secure=True,      # HTTPS only
        samesite="strict"
    )
    return {"access_token": tokens["access_token"]}
```

The client stores the access token in memory (a JavaScript variable — not `localStorage`) and attaches it to every protected request via the `Authorization` header:

```
Authorization: Bearer <access_token>
```

The refresh token lives in the browser's httpOnly cookie store. The browser sends it automatically on requests to the refresh endpoint — the client never touches it directly.

Client-side example:

```javascript
// After login — store access token in memory only
const { access_token } = await fetch("/login", {
    method: "POST",
    body: JSON.stringify({ username, password })
}).then(r => r.json())

// Every protected request — send access token in Authorization header
const profile = await fetch("/profile", {
    headers: { "Authorization": `Bearer ${access_token}` }
}).then(r => r.json())

// When access token expires — browser sends refresh cookie automatically
const refreshed = await fetch("/refresh", {
    method: "POST",
    credentials: "include"  // tells browser to send the httpOnly cookie
}).then(r => r.json())

const new_access_token = refreshed.access_token
```

### Handling login errors

```python
from gatevault import InvalidCredentialsError, UnauthorizedError, GuardError

try:
    tokens = await oauth.async_login(username, password)
except InvalidCredentialsError:
    return {"error": "invalid credentials"}, 401
except UnauthorizedError:
    return {"error": "invalid credentials"}, 401
except GuardError:
    return {"error": "authentication failed"}, 500
```

> Return the same error message for both `InvalidCredentialsError` and `UnauthorizedError`. Distinguishing between them tells an attacker which usernames exist in your system.

---

## Protecting Routes

`GateVault` wraps any function — sync or async — with token verification. The wrapped function never executes if the token is missing, expired, or invalid. On success, the decoded payload is injected as the `payload` keyword argument.

`gate.protected` automatically detects whether the decorated function is a coroutine (`async def`) and applies the appropriate wrapper. You use the same decorator for both.

### Setup

```python
from gatevault import GateVault

gate = GateVault(token_manager=tm)
```

---

### Sync Protection

```python
@gate.protected
def get_profile(payload=None):
    user_id = payload["user_id"]
    return db.get_user(user_id)

# call with token= keyword argument
result = get_profile(token="eyJhbGci...")
```

---

### Async Protection

```python
@gate.protected
async def get_profile(payload=None):
    user_id = payload["user_id"]
    return await db.get_user(user_id)

# await the call — gatevault detected async def and returns a coroutine
result = await get_profile(token="eyJhbGci...")
```

The token extraction and verification logic is identical in both cases. The only difference is that the async wrapper awaits the decorated function after injecting the payload.

---

### How the token reaches your function

In a real app, the client sends the token in the `Authorization` header. Your framework gives you access to that header. You extract the token string and pass it to the protected function:

```python
# FastAPI example
@app.get("/profile")
async def profile_route(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    try:
        return await get_profile(token=token)
    except (GuardError, UnauthorizedError):
        raise HTTPException(status_code=401, detail="unauthorized")
```

### Multiple protected routes

```python
@gate.protected
async def get_profile(payload=None):
    return await db.get_user(payload["user_id"])

@gate.protected
async def get_orders(payload=None):
    return await db.get_orders(payload["user_id"])

@gate.protected
async def update_settings(settings: dict, payload=None):
    return await db.update_settings(payload["user_id"], settings)
```

### Passing arguments alongside the token

Your function can accept any arguments alongside `payload`:

```python
@gate.protected
async def get_post(post_id: int, payload=None):
    user_id = payload["user_id"]
    post = await db.get_post(post_id)
    if post.owner_id != user_id:
        raise UnauthorizedError("not your post")
    return post

result = await get_post(post_id=7, token="eyJhbGci...")
```

### Role-based access using claims

```python
@gate.protected
def admin_only(payload=None):
    if payload.get("role") != "admin":
        raise UnauthorizedError("admin access required")
    return get_admin_data()

@gate.protected
async def moderator_or_above(payload=None):
    if payload.get("role") not in ("admin", "moderator"):
        raise UnauthorizedError("insufficient permissions")
    return await get_mod_tools()
```

### Handling guard errors

```python
from gatevault import GuardError, UnauthorizedError

try:
    result = await get_profile(token=incoming_token)
except GuardError as e:
    # token missing, expired, or malformed
    return {"error": str(e)}, 401
except UnauthorizedError as e:
    # invalid signature or permission check failed inside the function
    return {"error": str(e)}, 403
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
    tokens = await oauth.async_login(username, password)
except GatevaultError as e:
    return {"error": str(e)}, 401
```

### Catching specifically — different response per failure

```python
try:
    payload = tm.decode_token(token)
except TokenExpiredError:
    # access token expired — tell client to use refresh token
    return {"error": "token expired", "action": "refresh"}, 401
except InvalidTokenError:
    # signature mismatch — possible tampering, do not trust
    return {"error": "invalid token"}, 401
except TokenDecodeError:
    # token string is completely malformed — bad format
    return {"error": "malformed token"}, 400
```

### Catching by category

```python
try:
    payload = tm.decode_token(token)
except TokenError:
    # catches all three: TokenExpiredError, InvalidTokenError, TokenDecodeError
    return {"error": "token error"}, 401
```

```python
try:
    tokens = await oauth.async_login(username, password)
except GuardError:
    # catches InvalidCredentialsError and UnauthorizedError
    return {"error": "authentication failed"}, 401
```

### Real-world error handling pattern

```python
from gatevault import (
    InvalidCredentialsError, UnauthorizedError,
    TokenExpiredError, TokenDecodeError, InvalidTokenError, GuardError
)

async def handle_login(username: str, password: str):
    try:
        tokens = await oauth.async_login(username, password)
        return {"access_token": tokens["access_token"]}, 200
    except (InvalidCredentialsError, UnauthorizedError):
        return {"error": "invalid credentials"}, 401
    except GuardError:
        return {"error": "authentication failed"}, 500

async def handle_protected_request(token: str):
    try:
        return await get_profile(token=token)
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

Issued at `TokenManager` creation if the secret key is shorter than 32 bytes. HS256 requires at least 32 bytes per RFC 7518. This is a warning, not an error — your app will still run, but your tokens will be less secure.

```python
import warnings
from gatevault import TokenManager, ShortKeyWarning

# Suppress in tests where key length doesn't matter
warnings.filterwarnings("ignore", category=ShortKeyWarning)
tm = TokenManager(secret_key="short", access_expiry_minutes=15, refresh_expiry_days=7)
```

### Treating as an error in CI

```python
# Catch misconfigurations early — fail the build if key is too short
warnings.filterwarnings("error", category=ShortKeyWarning)
```

---

## Framework Integration

gatevault is framework-agnostic. The same library works across FastAPI, Flask, and Django — you wire it into each framework's request/response cycle in the same way: initialize once at startup, define protected functions with `@gate.protected`, and pass the token from the `Authorization` header into the protected function at request time.

| Framework | Recommended login method | Async support |
|---|---|---|
| FastAPI + async SQLAlchemy | `async_login` | Full — use `async def` protected functions |
| FastAPI + sync DB | `login` | N/A |
| Flask | `login` | Not applicable (Flask is sync) |
| Django (sync ORM) | `login` | N/A |
| Django 4.1+ async views | `async_login` | Full — use `async def` protected functions |
| Django REST Framework | `login` | N/A |

---

### FastAPI (Async)

The recommended FastAPI setup — uses `async_login`, `async def` protected functions, and async SQLAlchemy:

```python
import os
from fastapi import FastAPI, HTTPException, Response, Cookie, Depends, Header
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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


# Protected functions — async, defined once, reused across routes
@gate.protected
async def get_current_profile(payload=None):
    return await db.get_user(payload["user_id"])

@gate.protected
async def get_user_orders(payload=None):
    return await db.get_orders(payload["user_id"])


# Registration
@app.post("/register")
async def register(body: UserCreate, db: AsyncSession = Depends(get_db)):
    hashed = hash_password(body.password)
    new_user = User(email=body.email, hashed_password=hashed)
    db.add(new_user)
    await db.commit()
    return {"message": "registered"}


# Login — async DB lookup requires async_login
@app.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    response: Response = None,
    db: AsyncSession = Depends(get_db)
):
    async def _get_user(username: str):
        result = await db.execute(select(User).where(User.email == username))
        return result.scalar_one_or_none()

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


# Protected routes — extract token from header, pass to protected function
@app.get("/profile")
async def profile(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    try:
        return await get_current_profile(token=token)
    except (GuardError, UnauthorizedError):
        raise HTTPException(status_code=401, detail="unauthorized")


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


# Logout — clear the refresh token cookie
@app.post("/logout")
def logout(response: Response, refresh_token: str = Cookie(None)):
    response.delete_cookie("refresh_token")
    return {"message": "logged out"}
```

---

### FastAPI (Sync)

If you are using a synchronous database driver, use `login` and regular `def` protected functions:

```python
def get_user_from_db(username: str):
    return db.query(User).filter(User.email == username).first()

oauth = OAuthHandler(token_manager=tm, get_user=get_user_from_db)

@gate.protected
def get_current_profile(payload=None):
    return db.get_user(payload["user_id"])

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

@app.get("/profile")
def profile(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    try:
        return get_current_profile(token=token)
    except (GuardError, UnauthorizedError):
        raise HTTPException(status_code=401, detail="unauthorized")
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


def get_token():
    return request.headers.get("Authorization", "").replace("Bearer ", "")


@gate.protected
def get_current_profile(payload=None):
    return db.get_user(payload["user_id"])


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


@app.get("/profile")
def profile():
    try:
        return jsonify(get_current_profile(token=get_token()))
    except (GuardError, UnauthorizedError):
        return jsonify({"error": "unauthorized"}), 401


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

    new_access = tm.create_access_token(user_id=payload["user_id"])
    new_refresh = tm.create_refresh_token(user_id=payload["user_id"])

    response = make_response(jsonify({"access_token": new_access}))
    response.set_cookie(
        "refresh_token", new_refresh,
        httponly=True, secure=True, samesite="Strict"
    )
    return response


@app.post("/logout")
def logout():
    response = make_response(jsonify({"message": "logged out"}))
    response.delete_cookie("refresh_token")
    return response
```

---

### Django

gatevault works with Django's sync ORM out of the box. Use `login` with a sync `get_user`. For async views (Django 4.1+), use `async_login` with an async `get_user`.

#### Setup — `auth/gatevault_setup.py`

Create a dedicated setup file and import from it across your views. This avoids reinitializing gatevault objects on every request.

```python
# auth/gatevault_setup.py
import os
from gatevault import TokenManager, OAuthHandler, GateVault

tm = TokenManager(
    secret_key=os.environ["AUTH_SECRET_KEY"],
    access_expiry_minutes=15,
    refresh_expiry_days=7
)
gate = GateVault(token_manager=tm)


def get_user_from_db(username: str):
    from myapp.models import User
    try:
        return User.objects.get(email=username)
    except User.DoesNotExist:
        return None


oauth = OAuthHandler(token_manager=tm, get_user=get_user_from_db)
```

#### Views — `auth/views.py`

```python
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from gatevault import hash_password
from gatevault import (
    InvalidCredentialsError, UnauthorizedError,
    GuardError, TokenExpiredError, InvalidTokenError, TokenDecodeError
)
from .gatevault_setup import tm, oauth, gate
from .models import User


# Protected functions — defined once, called from any view
@gate.protected
def get_current_profile(payload=None):
    return User.objects.get(id=payload["user_id"])


# Registration
@csrf_exempt
@require_POST
def register(request):
    data = json.loads(request.body)
    hashed = hash_password(data["password"])
    User.objects.create(email=data["email"], hashed_password=hashed)
    return JsonResponse({"message": "registered"}, status=201)


# Login
@csrf_exempt
@require_POST
def login(request):
    data = json.loads(request.body)
    try:
        tokens = oauth.login(data["username"], data["password"])
    except (InvalidCredentialsError, UnauthorizedError):
        return JsonResponse({"error": "invalid credentials"}, status=401)

    response = JsonResponse({"access_token": tokens["access_token"], "token_type": "bearer"})
    response.set_cookie(
        "refresh_token",
        tokens["refresh_token"],
        httponly=True,
        secure=True,        # set to False in local development
        samesite="Strict"
    )
    return response


# Protected route — extract token from header, pass to protected function
@require_GET
def profile(request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    try:
        user = get_current_profile(token=token)
        return JsonResponse({"id": user.id, "email": user.email})
    except GuardError:
        return JsonResponse({"error": "unauthorized"}, status=401)
    except UnauthorizedError:
        return JsonResponse({"error": "forbidden"}, status=403)


# Token refresh — reads refresh token from httpOnly cookie
@csrf_exempt
@require_POST
def refresh(request):
    refresh_token = request.COOKIES.get("refresh_token")
    if not refresh_token:
        return JsonResponse({"error": "no refresh token"}, status=401)

    try:
        payload = tm.decode_token(refresh_token)
    except TokenExpiredError:
        return JsonResponse({"error": "session expired"}, status=401)
    except (InvalidTokenError, TokenDecodeError):
        return JsonResponse({"error": "invalid token"}, status=401)

    if payload["type"] != "refresh":
        return JsonResponse({"error": "wrong token type"}, status=400)

    new_access = tm.create_access_token(user_id=payload["user_id"])
    new_refresh = tm.create_refresh_token(user_id=payload["user_id"])

    response = JsonResponse({"access_token": new_access})
    response.set_cookie(
        "refresh_token", new_refresh,
        httponly=True, secure=True, samesite="Strict"
    )
    return response


# Logout — clear the refresh token cookie
@csrf_exempt
@require_POST
def logout(request):
    response = JsonResponse({"message": "logged out"})
    response.delete_cookie("refresh_token")
    return response
```

#### URL configuration — `auth/urls.py`

```python
from django.urls import path
from . import views

urlpatterns = [
    path("register/", views.register),
    path("login/", views.login),
    path("refresh/", views.refresh),
    path("logout/", views.logout),
    path("profile/", views.profile),
]
```

#### Django REST Framework

If you are using DRF, the same `gate.protected` functions work inside `APIView` or `@api_view` — extract the token from the `Authorization` header and pass it in:

```python
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from gatevault import GuardError, UnauthorizedError
from .gatevault_setup import gate


@gate.protected
def get_current_profile(payload=None):
    from myapp.models import User
    return User.objects.get(id=payload["user_id"])


@api_view(["GET"])
def profile(request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    try:
        user = get_current_profile(token=token)
        return Response({"id": user.id, "email": user.email})
    except GuardError:
        return Response({"error": "unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    except UnauthorizedError:
        return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
```

You can also use `APIView` for class-based views:

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status


class ProfileView(APIView):
    def get(self, request):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        try:
            user = get_current_profile(token=token)
            return Response({"id": user.id, "email": user.email})
        except (GuardError, UnauthorizedError):
            return Response({"error": "unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
```

#### Async Django views (Django 4.1+)

For async Django views, define an async `get_user` and use `async_login`:

```python
# auth/gatevault_setup.py — async variant
from django.contrib.auth import get_user_model

async def get_user_async(username: str):
    User = get_user_model()
    try:
        return await User.objects.aget(email=username)
    except User.DoesNotExist:
        return None

oauth_async = OAuthHandler(token_manager=tm, get_user=get_user_async)
```

```python
# auth/views.py — async login view
import json
from django.http import JsonResponse
from .gatevault_setup import oauth_async
from gatevault import InvalidCredentialsError, UnauthorizedError


async def login_async(request):
    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"}, status=405)
    data = json.loads(request.body)
    try:
        tokens = await oauth_async.async_login(data["username"], data["password"])
    except (InvalidCredentialsError, UnauthorizedError):
        return JsonResponse({"error": "invalid credentials"}, status=401)

    response = JsonResponse({"access_token": tokens["access_token"], "token_type": "bearer"})
    response.set_cookie(
        "refresh_token", tokens["refresh_token"],
        httponly=True, secure=True, samesite="Strict"
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
from gatevault import TokenExpiredError, InvalidTokenError, TokenDecodeError

tm = TokenManager(
    secret_key="your-very-secure-secret-key-32-bytes",
    access_expiry_minutes=30,
    refresh_expiry_days=14
)

# Create tokens after your own auth check
access = tm.create_access_token(user_id=1, role="admin", org_id=7)
refresh = tm.create_refresh_token(user_id=1)

# Decode and verify
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

```python
from gatevault import TokenManager, GateVault
from gatevault import GuardError, UnauthorizedError

tm = TokenManager(secret_key="...", access_expiry_minutes=15, refresh_expiry_days=7)
gate = GateVault(token_manager=tm)

# Works on both sync and async functions
@gate.protected
def get_dashboard(payload=None):
    return {"user_id": payload["user_id"]}

@gate.protected
async def get_dashboard_async(payload=None):
    return {"user_id": payload["user_id"]}

try:
    result = get_dashboard(token=incoming_token)
    result = await get_dashboard_async(token=incoming_token)
except GuardError:
    return {"error": "unauthorized"}, 401
except UnauthorizedError:
    return {"error": "forbidden"}, 403
```

---

## Token Refresh & Rotation

gatevault creates tokens on demand but does not manage storage or invalidation — that lives in your application. Without a refresh token store, a stolen refresh token is valid until it naturally expires, potentially days later.

### Why you need a refresh token store

With a store you can:
- Revoke tokens immediately on logout
- Detect token reuse (a sign of theft)
- Force re-login on password change or suspicious activity

A minimal SQL table for this:

```sql
CREATE TABLE refresh_tokens (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL
);
```

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

    # 2. Confirm it is a refresh token
    if payload["type"] != "refresh":
        return {"error": "wrong token type"}, 400

    # 3. Check for reuse — if already rotated, someone may have stolen it
    if not db.is_refresh_token_valid(refresh_token):
        db.revoke_all_tokens_for_user(payload["user_id"])
        return {"error": "token reuse detected, please log in again"}, 401

    # 4. Invalidate the old token
    db.revoke_refresh_token(refresh_token)

    # 5. Issue new pair
    new_access = tm.create_access_token(user_id=payload["user_id"])
    new_refresh = tm.create_refresh_token(user_id=payload["user_id"])

    # 6. Store the new refresh token
    db.store_refresh_token(new_refresh, user_id=payload["user_id"])

    return {"access_token": new_access, "refresh_token": new_refresh}
```

---

## Security Guide

### Secret key

- Use at least 32 bytes — gatevault warns you if you don't
- Generate with: `python -c "import secrets; print(secrets.token_hex(32))"`
- Store in an environment variable — never hardcode in source
- Rotating the key invalidates all existing tokens immediately — plan accordingly

### Token storage on the client

| Token | Where to store | Why |
|---|---|---|
| Access token | Memory (JS variable) | Short-lived, wiped on tab close, never persisted |
| Refresh token | httpOnly cookie | Invisible to JavaScript — safe from XSS |

Never store tokens in `localStorage` — any JavaScript running on the page, including injected scripts, can read it.

### What not to put in the payload

The JWT payload is base64 encoded, not encrypted. Anyone with the token string can decode and read it:

```python
# Fine — identifiers and non-sensitive metadata
tm.create_access_token(user_id=42, role="admin", org_id=7)

# Never do this — readable by anyone
tm.create_access_token(user_id=42, email="john@example.com", password_hash="$2b$...")
```

### Login enumeration

Return the same error for "user not found" and "wrong password":

```python
# Good — attacker learns nothing
except (InvalidCredentialsError, UnauthorizedError):
    return {"error": "invalid credentials"}, 401

# Bad — confirms the username exists
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
| `get_user` | `Callable[[str], Any \| None]` | User lookup function. Sync or async. Must return object with `id` and `hashed_password`, or `None`. |

| Method | Returns | Description |
|---|---|---|
| `login(username, password)` | `dict` | Authenticates synchronously. Use when `get_user` is a regular function. Returns `{"access_token", "refresh_token", "token_type"}`. |
| `async_login(username, password)` | `Coroutine[dict]` | Authenticates asynchronously. Use when `get_user` is `async def`. Must be called with `await`. |

---

### `GateVault(token_manager)`

| Parameter | Type | Description |
|---|---|---|
| `token_manager` | `TokenManager` | Configured TokenManager instance. |

| Method | Returns | Description |
|---|---|---|
| `protected(f)` | `Callable` | Decorator. Verifies token before executing `f`. Works on both sync and async functions. Injects decoded payload as `payload` kwarg on success. |

---

### `hash_password(plain) -> str`

| Parameter | Type | Description |
|---|---|---|
| `plain` | `str` | Plain text password. |

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

Tying gatevault to FastAPI or Flask would limit who can use it. Auth logic — hashing, signing, verifying — has nothing to do with HTTP. Pure Python means it works anywhere Python runs.

**Both sync and async throughout**

`async_login` and async-aware `gate.protected` were added to support async ORMs like async SQLAlchemy without requiring a separate library or workaround. The sync and async paths are intentionally separate in `OAuthHandler` — calling the wrong one for your `get_user` type fails loudly rather than silently misbehaving. `gate.protected` unifies both under one decorator by detecting the function type at decoration time.

**Class-based `TokenManager`**

The secret key and expiry settings are configuration — they belong on an instance, not passed into every function call. Configure once at startup, share everywhere without threading arguments through every call.

**Shared `TokenManager` across `OAuthHandler` and `GateVault`**

`OAuthHandler` creates tokens. `GateVault` verifies them. The shared `TokenManager` instance is the trust anchor — same secret key in, same secret key out.

**Payload injected as a keyword argument**

`payload=payload` is explicit. The decorated function always knows where its auth data comes from. Positional injection would silently break functions whose arguments don't match the expected order.

**Wrapping third-party exceptions**

`PyJWT` and `bcrypt` exceptions never surface through the gatevault API. Consumers only need to know gatevault exceptions. If an underlying library changes its exception names in a future version, only gatevault updates.

**`verify_password` returns bool, not raises**

A wrong password is an expected outcome, not an exceptional one. The caller decides whether to raise, log, increment a failed attempt counter, or do something else entirely.

---

## Known Limitations

- Refresh token invalidation is not built in — you need a database or cache to track and revoke issued refresh tokens
- Only HS256 (symmetric signing) is supported — RS256 (asymmetric keypair) is not yet available
- No built-in rate limiting on login attempts — implement at the application or infrastructure level

---

## Future Improvements

- RS256 support for asymmetric key signing
- Built-in token blocklist interface for revocation
- Role-based access control helpers on `GateVault`
- FastAPI and Flask integration packages as optional extras

---

## Contributing

Contributions are welcome. Open an issue first to discuss what you want to change, especially for anything touching the security-sensitive parts.

```bash
git clone https://github.com/RichardOyelowo/gatevault
cd gatevault
pip install -e ".[dev]"
pytest tests/ -v
```

---

## License

Apache 2.0 — see [LICENSE](./LICENSE) for details.

---
**Built by Richard for the love of development.**
