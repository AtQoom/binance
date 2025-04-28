from core.indicators import calculate_rsi
from config.constants import *

def check_entry_signal(price_list, rsi_threshold_long=24, rsi_threshold_short=76):
    rsi = calculate_rsi(price_list)

    if rsi < rsi_threshold_long:
        return "long"
    elif rsi > rsi_threshold_short:
        return "short"
    else:
        return None

def check_exit_signal(price_list, long_position):
    rsi = calculate_rsi(price_list)

    if long_position and rsi >= 70:
        return "partial_exit"
    elif not long_position and rsi <= 30:
        return "partial_exit"
    else:
        return None
