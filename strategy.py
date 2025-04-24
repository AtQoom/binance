from gateio_api import place_order, get_equity, get_market_price, get_position_size
from state import load_state, save_state
from ha import fetch_ohlcv, compute_heikin_ashi
import math

LEVERAGE = 6
RISK_PCT = 0.16
MIN_QTY = 1

def handle_signal(signal, strength):
    state = load_state()
    if signal == "ENTRY LONG":
        place_order("sell", 0, reduce_only=True)
        side = "buy"
    elif signal == "ENTRY SHORT":
        place_order("buy", 0, reduce_only=True)
        side = "sell"
    else:
        return {"error": "Invalid signal"}

    equity = get_equity()
    price = get_market_price()
    if equity == 0 or price == 0:
        return {"error": "잔고 또는 시세 오류"}

    qty = max(int((equity * RISK_PCT * LEVERAGE * strength) / price), MIN_QTY)
    place_order(side, qty)

    state["side"] = side
    state["entry_price"] = price
    state["qty"] += qty
    state["entry_round"] += 1
    save_state(state)

    return {"status": "주문 전송", "side": side, "qty": qty}

def check_exit_condition():
    state = load_state()
    if state["side"] is None or state["qty"] <= 0:
        return

    df = fetch_ohlcv()
    if df.empty:
        return

    ha = compute_heikin_ashi(df)
    last_6 = ha.tail(6)
    if len(last_6) < 6:
        return

    recent_colors = last_6["HA_color"].tolist()
    trend_color = recent_colors[0]
    if all(c == trend_color for c in recent_colors[:5]) and recent_colors[5] != trend_color:
        price = get_market_price()
        if state["side"] == "buy" and price > state["entry_price"]:
            print("[🎯 익절 조건 충족] 롱 포지션 절반 익절")
            place_order("sell", 0, reduce_only=True)
            state["qty"] = get_position_size()
            state["partial_exit_count"] += 1
            save_state(state)
        elif state["side"] == "sell" and price < state["entry_price"]:
            print("[🎯 익절 조건 충족] 숏 포지션 절반 익절")
            place_order("buy", 0, reduce_only=True)
            state["qty"] = get_position_size()
            state["partial_exit_count"] += 1
            save_state(state)