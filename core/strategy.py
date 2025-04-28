# core/strategy.py

from config.constants import *

class Strategy:
    def __init__(self):
        pass

    def should_enter_long(self, rsi):
        return rsi > RSI_LONG_ENTRY

    def should_enter_short(self, rsi):
        return rsi < RSI_SHORT_ENTRY

    def is_heavy_entry_long(self, rsi):
        return rsi < RSI_HEAVY_LONG

    def is_heavy_entry_short(self, rsi):
        return rsi > RSI_HEAVY_SHORT

    def should_take_first_profit(self, current_price, avg_price, is_long):
        if is_long:
            return (current_price - avg_price) / avg_price >= FIRST_TAKE_PROFIT
        else:
            return (avg_price - current_price) / avg_price >= FIRST_TAKE_PROFIT

    def should_take_second_profit(self, rsi, is_long):
        if is_long:
            return rsi >= SECOND_TAKE_PROFIT_RSI_LONG
        else:
            return rsi <= SECOND_TAKE_PROFIT_RSI_SHORT

    def is_opposite_signal(self, rsi, is_long):
        if is_long:
            return rsi < RSI_LONG_ENTRY
        else:
            return rsi > RSI_SHORT_ENTRY
