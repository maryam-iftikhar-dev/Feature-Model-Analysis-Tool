from logger import log_event


def send_order_notification(order):
    log_event("Notifications", f"Order notification for {order.user.email}")
    return True
