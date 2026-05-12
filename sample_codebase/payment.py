from auth import login_user
from logger import log_event


def process_payment(user, amount: float) -> bool:
    if not user.authenticated:
        return False
    log_event("Payment", f"Processing {amount} for {user.email}")
    return True
