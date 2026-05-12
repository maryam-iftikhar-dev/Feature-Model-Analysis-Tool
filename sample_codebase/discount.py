from inventory import reserve_items


def calculate_discount(user, items):
    if len(items) > 1:
        return 10.0
    return 0.0


def apply_discount(user, items):
    reserve_items(items)
    return calculate_discount(user, items)
