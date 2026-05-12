from logger import log_event


def reserve_items(items):
    log_event("Inventory", f"Reserving {len(items)} items")
    return True
