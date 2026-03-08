import jwt
import warnings
from .warnings import ShortKeyWarning
from datetime import datetime, timezone, timedelta
from .exceptions import TokenExpiredError, InvalidTokenError, TokenDecodeError


class TokenManager:
    """Manages JWT access and refresh token creation and verification.

    This class handles the full JWT lifecycle — signing tokens on login and
    decoding/verifying them on subsequent requests. Tokens are signed using
    the HS256 algorithm with a shared secret key.

    Args:
        secret_key: The secret key used to sign tokens. Must be at least
                    32 bytes for HS256 security. A warning is issued if shorter.
        access_expiry_minutes: Lifetime of access tokens in minutes.
                               Typical values are 15–60 minutes.
        refresh_expiry_days: Lifetime of refresh tokens in days.
                             Typical values are 7–30 days.

    Example::

        tm = TokenManager(
            secret_key="your-very-secure-secret-key-here",
            access_expiry_minutes=15,
            refresh_expiry_days=7
        )
        access_token = tm.create_access_token(user_id=1)
        refresh_token = tm.create_refresh_token(user_id=1)
        payload = tm.decode_token(access_token)
    """

    def __init__(self, secret_key: str, access_expiry_minutes: int, refresh_expiry_days: int) -> None:
        self.secret_key = secret_key
        self.access_expiry = access_expiry_minutes
        self.refresh_expiry = refresh_expiry_days

        if len(secret_key.encode("utf-8")) < 32:
            warnings.warn(
                "Secret key is shorter than the recommended 32 bytes for HS256. "
                "Consider using a longer key in production.",
                ShortKeyWarning
            )

    def _create_token(self, user_id: int, token_type: str, exp: timedelta, **kwargs) -> str:
        """Internal method for building and signing a JWT payload.

        Args:
            user_id: The ID of the user to encode in the token.
            token_type: Either ``"access"`` or ``"refresh"``.
            exp: The token lifetime as a timedelta.
            **kwargs: Additional claims to include in the payload.

        Returns:
            A signed JWT string.
        """
        payload = {
            "user_id": user_id,
            "exp": datetime.now(timezone.utc) + exp,
            "type": token_type,
            **kwargs
        }
        return jwt.encode(payload, self.secret_key, "HS256")

    def create_access_token(self, user_id: int, **kwargs) -> str:
        """Create a signed short-lived JWT access token.

        Access tokens are intended to be sent with every authenticated request.
        They expire quickly to limit exposure if compromised.

        Args:
            user_id: The ID of the user to encode in the token.
            **kwargs: Additional claims to include in the token payload
                      (e.g. ``role="admin"``).

        Returns:
            A signed JWT access token string.

        Example::

            token = tm.create_access_token(user_id=42, role="admin")
        """
        return self._create_token(user_id, "access", timedelta(minutes=self.access_expiry), **kwargs)

    def create_refresh_token(self, user_id: int, **kwargs) -> str:
        """Create a signed long-lived JWT refresh token.

        Refresh tokens are used only to obtain a new access token when the
        current one expires. They should be stored securely and rotated on
        each use.

        Args:
            user_id: The ID of the user to encode in the token.
            **kwargs: Additional claims to include in the token payload.

        Returns:
            A signed JWT refresh token string.

        Example::

            token = tm.create_refresh_token(user_id=42)
        """
        return self._create_token(user_id, "refresh", timedelta(days=self.refresh_expiry), **kwargs)

    def decode_token(self, token: str) -> dict:
        """Decode and verify a JWT token.

        Verifies the token signature using the secret key and checks that
        the token has not expired. Returns the decoded payload on success.

        Args:
            token: The JWT string to decode.

        Returns:
            The decoded payload as a dictionary containing at minimum
            ``user_id``, ``exp``, and ``type`` claims.

        Raises:
            TokenExpiredError: If the token has expired.
            TokenDecodeError: If the token is malformed or cannot be decoded.
            InvalidTokenError: If the token signature is invalid.

        Example::

            payload = tm.decode_token(token)
            user_id = payload["user_id"]
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
        except jwt.exceptions.InvalidSignatureError:
            raise InvalidTokenError
        except jwt.DecodeError:
            raise TokenDecodeError
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError
        except jwt.InvalidTokenError:
            raise InvalidTokenError

        return payload
