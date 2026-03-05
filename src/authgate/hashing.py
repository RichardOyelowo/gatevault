import bcrypt


def hash_password(plain: str) -> str:
    """Hash a plain text password using bcrypt.

    Args:
        plain: The plain text password to hash.

    Returns:
        The bcrypt hashed password as a string.
    """
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain text password against a bcrypt hash.

    Args:
        plain: The plain text password to check.
        hashed: The bcrypt hash to check against.

    Returns:
        True if the password matches, False otherwise.
    """
    return bcrypt.checkpw(plain.encode(), hashed.encode())
