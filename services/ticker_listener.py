# services/exit_manager.py

from core.trader import place_order
from config.constants import LEVERAGE

def exit_long(quantity):
    place_order("sell", quantity, LEVERAGE)

def exit_short(quantity):
    place_order("buy", quantity, LEVERAGE)
