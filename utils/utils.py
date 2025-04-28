# utils/utils.py

def calculate_profit(entry_price, current_price, leverage):
    profit = (current_price - entry_price) / entry_price * leverage
    return profit
