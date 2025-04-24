from gateio_api import place_order, get_equity, get_market_price, get_position_size
from state import load_state, save_state
from ha import fetch_ohlcv, compute_heikin_ashi
import time

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

def strategy_loop():
    while True:
        try:
            check_exit_conditions()
        except Exception as e:
            print(f"[ERROR] 전략 루프 실패: {e}")
        time.sleep(60)

def check_exit_conditions():
    state = load_state()
    if state["side"] is None or state["qty"] <= 0:
        return

    df = fetch_ohlcv()
    if df.empty or len(df) < 20:
        return

    ha = compute_heikin_ashi(df)
    recent = ha.tail(10)
    colors = recent["HA_color"].tolist()

    current_price = get_market_price()
    entry_price = state["entry_price"]
    side = state["side"]

    def half_exit():
        place_order("sell" if side == "buy" else "buy", 0, reduce_only=True)
        state["qty"] = get_position_size()
        state["partial_exit_count"] += 1
        save_state(state)

    # 조건 2: 5봉 같은색 + 반대봉 + 수익 중
    if all(colors[-6:-1]) == colors[-6] and colors[-1] != colors[-6]:
        if side == "buy" and current_price > entry_price:
            print("[🔁 조건2] 롱 절반 익절")
            half_exit()
        elif side == "sell" and current_price < entry_price:
            print("[🔁 조건2] 숏 절반 익절")
            half_exit()
        return

    # 조건 3: 4봉 → 반대 1봉 → 3봉 같은색 → 반대 1봉
    trend = colors[-9:]
    if (trend[0] == trend[1] == trend[2] == trend[3] and
        trend[4] != trend[3] and
        trend[5] == trend[6] == trend[7] and
        trend[8] != trend[7]):
        if side == "buy" and current_price > entry_price:
            print("[🔁 조건3] 롱 절반 익절")
            half_exit()
        elif side == "sell" and current_price < entry_price:
            print("[🔁 조건3] 숏 절반 익절")
            half_exit()