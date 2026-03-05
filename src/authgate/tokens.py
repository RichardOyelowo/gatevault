import jwt
from datetime import datetime, timezone, timedelta
from .exceptions import TokenError, TokenExpiredError, InvalidTokenError, TokenDecodeError


class TokenManager:
    def __init__(self, secret_key: str, acesss_expiry_minutes: int, access_expiry_days: int) -> str:
        self.secret_key = secret_key
        self.access_expiry_minutes = acesss_expiry_minutes
        self.access_expiry_days = access_expiry_days


    def _create_token(self, user_id: int, token_type: str, exp: timedelta, **kwargs) -> str:
        payload = {
            "user_id": user_id,
            "exp": datetime.utcnow() + exp,
            "type": token_type,
            **kwargs
        }

        return jwt.encode(payload, secret_key, "H256")


    def create_access_token(self, user_id: int, **kwargs) -> str:

        return self._create_token(user_id, token_type="access", self.access_expiry_minutes, **kwargs)


    def create_refresh_token(self, user_id: int, **kwargs) -> str:
        
        return self._create_token(user_id, token_type="refresh", self.access_expiry_days, **kwargs)
