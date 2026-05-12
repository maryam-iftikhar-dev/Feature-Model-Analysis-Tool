from auth import login_user
from checkout import start_checkout
from notifications import send_order_notification


def run_shop():
    user = login_user("customer@example.com")
    if user:
        order = start_checkout(user)
        send_order_notification(order)


if __name__ == "__main__":
    run_shop()
