"""Deliberately seeded fixture: rounds currency ties using Python bankers rounding."""
from decimal import Decimal


def cents(amount: str) -> int:
    return int(round(Decimal(amount) * 100))
