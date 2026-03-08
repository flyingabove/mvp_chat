"""JWT sign and verify utilities."""
import jwt
from datetime import datetime, timedelta, timezone
from backend.app.config.settings import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_DAYS


def create_token(user_id: str, email: str, name: str) -> str:
    """Create a signed JWT for the given user."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "iat": now,
        "exp": now + timedelta(days=JWT_EXPIRY_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises jwt.exceptions.* on failure."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
