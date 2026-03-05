class AuthgateError(Exception):
    """Base exception for all authgate errors."""


# --- Token Exceptions ---

class TokenError(AuthgateError):
    """Base exception for JWT-related errors."""


class TokenExpiredError(TokenError):
    """Raised when a JWT token has expired."""


class InvalidTokenError(TokenError):
    """Raised when a token is malformed or has an invalid signature."""


class TokenDecodeError(TokenError):
    """Raised when a token cannot be decoded."""


# --- Hashing Exceptions ---

class HashingError(AuthgateError):
    """Base exception for password hashing errors."""


class InvalidCredentialsError(HashingError):
    """Raised when a password does not match the stored hash."""


# --- Guard Exceptions ---

class GuardError(AuthgateError):
    """Base exception for auth guard errors."""


class UnauthorizedError(GuardError):
    """Raised when a request fails an auth guard check."""
