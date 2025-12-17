import jwt
import os
from datetime import datetime, timedelta, timezone
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from dotenv import load_dotenv

load_dotenv()

# ================== CONFIG ==================

JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_IN_PRODUCTION")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 24

ALLOWED_EXACT = {"gmail.com"}
ALLOWED_SUFFIXES = (
    ".edu", ".edu.in", ".ac.in", ".ac.uk", ".edu.au", ".edu.sg"
)

# ================== EMAIL VALIDATION ==================

def is_allowed_email(email: str) -> bool:
    if not email or "@" not in email:
        return False

    domain = email.split("@")[-1].lower()
    return (
        domain in ALLOWED_EXACT
        or any(domain.endswith(suffix) for suffix in ALLOWED_SUFFIXES)
    )

# ================== JWT HELPERS ==================

def create_verification_token(email: str) -> str:
    email = email.lower().strip()

    payload = {
        "email": email,
        "type": "email_verification",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS),
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_verification_token(token: str) -> str | None:
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )

        if payload.get("type") != "email_verification":
            return None

        return payload.get("email")

    except ExpiredSignatureError:
        return None
    except InvalidTokenError:
        return None

def create_unsubscribe_token(email: str) -> str:
    email = email.lower().strip()

    payload = {
        "email": email,
        "type": "unsubscribe",
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_unsubscribe_token(token: str) -> str | None:
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )

        if payload.get("type") != "unsubscribe":
            return None

        return payload.get("email")

    except InvalidTokenError:
        return None

# ================== TEST ==================

if __name__ == "__main__":
    token = create_verification_token("nanithota18102004@gmail.com")
    print("TOKEN:", token)

    email = verify_verification_token(token)
    print("DECODED EMAIL:", email)
