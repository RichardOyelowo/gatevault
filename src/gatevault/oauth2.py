from .tokens import TokenManager
from .hashing import verify_password
from .exceptions import GuardError, InvalidCredentialsError, UnauthorizedError


class OAuthHandler:
    """Handles the OAuth2 password credentials flow for user authentication.

    This class wires together user lookup, password verification, and token
    generation into a single login handler. It follows the OAuth2 Resource
    Owner Password Credentials flow.

    Args:
        token_manager: A configured TokenManager instance used to create
                       access and refresh tokens.
        get_user: A callable that accepts a username string and returns a
                  user object with ``id`` and ``hashed_password`` attributes,
                  or None if the user does not exist.

    Example::

        tm = TokenManager(secret_key="...", access_expiry_minutes=15, refresh_expiry_days=7)
        handler = OAuthHandler(token_manager=tm, get_user=get_user_from_db)
        tokens = handler.login("john@example.com", "mypassword")
    """

    def __init__(self, token_manager: TokenManager, get_user) -> None:
        self.token_manager = token_manager
        self.get_user = get_user

    def login(self, username: str, password: str) -> dict:
        """Authenticate a user and return access and refresh tokens.

        Looks up the user by username, verifies the provided password against
        the stored hash, then issues a new access and refresh token pair.

        Args:
            username: The user's username or email address.
            password: The plain text password provided by the user.

        Returns:
            A dictionary containing:
                - ``access_token``: A short-lived JWT for authenticating requests.
                - ``refresh_token``: A long-lived JWT for obtaining new access tokens.
                - ``token_type``: Always ``"bearer"``.

        Raises:
            InvalidCredentialsError: If no user is found with the given username.
            UnauthorizedError: If the password does not match the stored hash.
            GuardError: If token creation fails unexpectedly.
        """
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