from .tokens import TokenManager
from .hashing import verify_password
from .exceptions import GuardError, InvalidCredentialsError, UnauthorizedError


class OAuthHandler:
    """Handles the OAuth2 password flow for user authentication.

    Args:
        token_manager: A configured TokenManager instance.
        get_user: A callable that accepts a username and returns a user object
                  with a hashed_password attribute, or None if not found.
    """

    def __init__(self, token_manager: TokenManager, get_user) -> None:
        self.token_manager = token_manager
        self.get_user = get_user


    def login(self, username: str, password: str) -> dict:
        user = self.get_user(username)

        if not user:
            raise InvalidCredentialsError("no user found")
                    
        if not verify_password(password, user.hashed_password):
            raise UnauthorizedError("user password mismatched")

        try:
            data = {
                "access_token": self.token_manager.create_access_token(user.id),
                "refresh_token": self.token_manager.create_refresh_token(user.id),
                "token_type": "bearer"
            }
        except Exception as e:
            raise GuardError("invalid user id or token_manager error") from e

        return data
