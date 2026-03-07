from functools import wraps
from .tokens import TokenManager
from .exceptions import GuardError, UnauthorizedError, TokenDecodeError, TokenExpiredError, InvalidTokenError



class GateVault:
    """Protects routes and functions by verifying JWT tokens before execution.

    GateVault acts as a decorator factory — wrapping any function with token
    verification logic so protected routes never execute without a valid token.
    The decoded payload is injected into the wrapped function as a ``payload``
    keyword argument.

    Args:
        token_manager: A configured TokenManager instance used to decode
                       and verify incoming tokens.

    Example::

        tm = TokenManager(secret_key="...", access_expiry_minutes=15, refresh_expiry_days=7)
        gate = GateVault(token_manager=tm)

        @gate.protected
        def get_profile(payload=None):
            user_id = payload["user_id"]
            return f"Hello user {user_id}"
    """

    def __init__(self, token_manager: TokenManager) -> None:
        self.token_manager = token_manager

    def protected(self, f):
        """Decorator that enforces JWT authentication on the wrapped function.

        Extracts and verifies the token before the function executes. On
        success, the decoded payload is passed into the wrapped function as
        the ``payload`` keyword argument. On failure, an appropriate exception
        is raised before the function is ever called.

        Args:
            f: The function to protect. It should accept a ``payload`` keyword
               argument to receive the decoded token data.

        Returns:
            The wrapped function with token verification applied.

        Raises:
            GuardError: If no token is provided, the token cannot be decoded,
                        or the token has expired.
            UnauthorizedError: If the token signature is invalid.

        Example::

            @gate.protected
            def get_dashboard(payload=None):
                return f"Welcome user {payload['user_id']}"

            # Calling the protected function:
            get_dashboard(token="eyJhbGci...")
        """
        @wraps(f)
        def decorated_function(token, *args, **kwargs):
            if not token:
                raise GuardError("No token provided")
            try:
                payload = self.token_manager.decode_token(token)
            except TokenDecodeError:
                raise GuardError("Unable to decode token")
            except TokenExpiredError:
                raise GuardError("Token has expired")
            except InvalidTokenError:
                raise UnauthorizedError("Invalid token")
            return f(*args, payload=payload, **kwargs)
        return decorated_function
