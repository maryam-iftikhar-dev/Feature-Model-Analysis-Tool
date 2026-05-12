from dataclasses import dataclass


@dataclass
class User:
    email: str
    authenticated: bool = False


@dataclass
class Order:
    user: User
    items: list
    total: float
    shipped: dict
