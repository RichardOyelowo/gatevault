import bcrypt
from .exceptions import HashingError


def hash_password(plain: str) -> str:
    """Hash a plain text password using bcrypt.

    Args:
        plain: The plain text password to hash.

    Returns:
        The bcrypt hashed password as a string.
    """
    try:
        return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    except Exception as e:
        raise HashingError("failed to hash password") from e


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain text password against a bcrypt hash.

    Args:
        plain: The plain text password to check.
        hashed: The bcrypt hash to check against.

    Returns:
        True if the password matches, False otherwise.
    """
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
