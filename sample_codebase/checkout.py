from inventory import reserve_items
from payment import process_payment
from shipping import schedule_shipping
from promotions import apply_promotions
from models import Order, User


def start_checkout(user: User) -> Order:
    items = ["widget"]
    reserve_items(items)
    discount = apply_promotions(user, items)
    payment_success = process_payment(user, 100.0 - discount)
    shipment = schedule_shipping(items)
    return Order(user=user, items=items, total=100.0 - discount, shipped=shipment)
