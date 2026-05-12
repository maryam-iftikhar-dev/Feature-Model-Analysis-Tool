from logger import log_event
from models import User


def login_user(email: str) -> User:
    log_event("Authentication", f"Login attempt for {email}")
    return User(email=email, authenticated=True)
