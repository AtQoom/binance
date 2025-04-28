# core/trader.py 예시

def calculate_entry_qty(account_balance, price, strong_entry=False):
    percent = ENTRY_PERCENT_STRONG if strong_entry else ENTRY_PERCENT_NORMAL
    usd_amount = account_balance * percent
    qty = usd_amount / price
    return qty
