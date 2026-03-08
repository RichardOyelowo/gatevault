class GatevaultError(Exception):
    """Base exception for all gatevault errors."""


# --- Token Exceptions ---

class TokenError(GatevaultError):
    """Base exception for JWT-related errors."""


class TokenExpiredError(TokenError):
    """Raised when a JWT token has expired."""


class InvalidTokenError(TokenError):
    """Raised when a token is malformed or has an invalid signature."""


class TokenDecodeError(TokenError):
    """Raised when a token cannot be decoded."""


# --- Hashing Exceptions ---

class HashingError(GatevaultError):
    """Base exception for password hashing errors."""


# --- Guard Exceptions ---

class GuardError(GatevaultError):
    """Base exception for auth guard errors."""


class InvalidCredentialsError(GuardError):
    """Raised when a password does not match the stored hash."""


class UnauthorizedError(GuardError):
    """Raised when a request fails an auth guard check."""