from fastapi import HTTPException
from datetime import datetime, timedelta, timezone
from slowapi import Limiter
from slowapi.util import get_remote_address

import os
import jwt
import re


SECRET_KEY = os.environ["SECRET_KEY"]
ALGORITHM = 'HS256'
EMAIL_REGEX = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
limiter = Limiter(key_func=get_remote_address)
FAIL_LIMIT = 5
FAIL_WINDOW = timedelta(minutes=15)
failures : dict[str, list[datetime]] = {}

def create_token(id):
    data = {
        'sub': str(id),
        'exp': datetime.now(timezone.utc) + timedelta(minutes=30)
    }
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def token_verify(credentials):
    try:
        payload = jwt.decode(
            credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail='Invalid or expired token')
    return payload


def is_valid_email(email: str) -> bool:
    return bool(re.match(EMAIL_REGEX, email))


def too_many_failures(email: str):
    now = datetime.now(timezone.utc)
    recent = [t for t in failures.get(email, []) if now - t < FAIL_WINDOW]
    failures[email] = recent
    return len(recent) >= FAIL_LIMIT