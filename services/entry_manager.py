# services/entry_manager.py

from core.trader import place_order
from config.constants import LEVERAGE

def enter_long(quantity):
    place_order("buy", quantity, LEVERAGE)

def enter_short(quantity):
    place_order("sell", quantity, LEVERAGE)
