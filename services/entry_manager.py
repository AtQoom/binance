from config.constants import *
from core.position_manager import set_position

def enter_position(direction, account_balance, price, strong=False):
    percent = ENTRY_PERCENT_STRONG if strong else ENTRY_PERCENT_NORMAL
    usd_amount = account_balance * percent
    qty = usd_amount / price

    set_position(direction)
    return qty
