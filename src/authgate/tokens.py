import jwt
from datetime import datetime, timezone, timedelta
from .exceptions import TokenError, TokenExpiredError, InvalidTokenError, TokenDecodeError


class TokenManager:
    def __init__(self, secret_key: str, access_expiry_minutes: int, refresh_expiry_days: int) -> None:
        self.secret_key = secret_key
        self.access_expiry = access_expiry_minutes
        self.refresh_expiry = refresh_expiry_days


    def _create_token(self, user_id: int, token_type: str, exp: timedelta, **kwargs) -> str:
        payload = {
            "user_id": user_id,
            "exp": datetime.now(timezone.utc) + exp,
            "type": token_type,
            **kwargs
        }
        return jwt.encode(payload, self.secret_key, "HS256")


    def create_access_token(self, user_id: int, **kwargs) -> str:

        return self._create_token(user_id, "access", timedelta(minutes=self.access_expiry), **kwargs)


    def create_refresh_token(self, user_id: int, **kwargs) -> str:
        
        return self._create_token(user_id, "refresh", timedelta(days=self.refresh_expiry), **kwargs)


    def decode_token(self, token: str) -> dict:
    
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
