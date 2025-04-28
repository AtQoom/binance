def calculate_heikin_ashi(open_price, high_price, low_price, close_price):
    ha_close = (open_price + high_price + low_price + close_price) / 4
    return ha_close
