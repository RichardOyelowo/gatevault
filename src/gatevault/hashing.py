import bcrypt
from .exceptions import HashingError


def hash_password(plain: str) -> str:
    """Hash a plain text password using bcrypt.

    Args:
        plain: The plain text password to hash(string, not bytes).

    Returns:
        The bcrypt hashed password as a string.

    Example::
        
        password = "user_secret_string"
        hash_password(password)
    """
    try:
        return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    except Exception as e:
        raise HashingError("failed to hash password") from e


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain text password against a bcrypt hash.

    Args:
        plain: The plain text password to check(string, not bytes).
        hashed: The bcrypt hash to check against(string, not bytes).

    Returns:
        True if the password matches, False otherwise.

    Example::
        
        password = "user_string_entry:not encoded"
        saved_password = "hashed_values of the user password from database"
        verify_password(password, saved_password)
    """
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
