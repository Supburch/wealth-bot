import decimal
from decimal import Decimal

# Set global decimal context rounding
decimal.getcontext().rounding = decimal.ROUND_HALF_UP

TWOPLACES = Decimal("0.01")
