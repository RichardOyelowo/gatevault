import jwt
from .warnings import ShortKeyWarning
from datetime import datetime, timezone, timedelta
from .exceptions import TokenError, TokenExpiredError, InvalidTokenError, TokenDecodeError


class TokenManager:
    """Manages JWT access and refresh token creation and verification.

        Args:
            secret_key: The secret key used to sign tokens. Must be at least 32 bytes.
            access_expiry_minutes: Lifetime of access tokens in minutes.
            refresh_expiry_days: Lifetime of refresh tokens in days.
    """

    def __init__(self, secret_key: str, access_expiry_minutes: int, refresh_expiry_days: int) -> None:
        self.secret_key = secret_key
        self.access_expiry = access_expiry_minutes
        self.refresh_expiry = refresh_expiry_days
        
        if len(secret_key.encode()) < 32:
            warnings.warn("secret key is shorter than recommended 32 bytes", ShortKeyWarning)


    def _create_token(self, user_id: int, token_type: str, exp: timedelta, **kwargs) -> str:
        """Internal method for building a signed JWT payload."""

        payload = {
            "user_id": user_id,
            "exp": datetime.now(timezone.utc) + exp,
            "type": token_type,
            **kwargs
        }
        return jwt.encode(payload, self.secret_key, "HS256")


    def create_access_token(self, user_id: int, **kwargs) -> str:
        """Create a signed JWT access token.

            Args:
                user_id: The ID of the user to encode in the token.
                **kwargs: Additional claims to include in the token payload.

            Returns:
                A signed JWT access token string.
        """

        return self._create_token(user_id, "access", timedelta(minutes=self.access_expiry), **kwargs)


    def create_refresh_token(self, user_id: int, **kwargs) -> str:
        """Create a signed JWT refresh token.

            Args:
                user_id: The ID of the user to encode in the token.
                **kwargs: Additional claims to include in the token payload.

            Returns:
                A signed JWT refresh token string.
        """
        
        return self._create_token(user_id, "refresh", timedelta(days=self.refresh_expiry), **kwargs)


    def decode_token(self, token: str) -> dict:
        """Decode and verify a JWT token.

            Args:
                token: The JWT string to decode.

            Returns:
                The decoded payload as a dictionary.

            Raises:
                TokenExpiredError: If the token has expired.
                TokenDecodeError: If the token is malformed.
                InvalidTokenError: If the token signature is invalid.
        """

        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])

        # invalid/malformed token
        except jwt.DecodeError:
            raise TokenDecodeError
        
        # expired token
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError
        
        # invalid secret_key
        except jwt.InvalidTokenError:
            raise InvalidTokenError
        
        return payload
