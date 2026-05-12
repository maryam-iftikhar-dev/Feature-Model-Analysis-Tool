from discount import apply_discount


def apply_promotions(user, items):
    discount = apply_discount(user, items)
    return discount
