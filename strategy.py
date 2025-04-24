import time
from gateio_api import get_market_price, place_order, get_position_size, SYMBOL

# 상태 추적용
state = {
    "side": None,
    "entry_price": None,
    "entry_count": 0,
    "last_color": None,
    "color_count": 0
}

def handle_signal(signal, strength):
    print(f"[📊 전략 처리] {signal=} {strength=}")
    return {
        "status": "신호 처리 완료",
        "signal": signal,
        "strength": strength
    }

def reset_state():
    state["side"] = None
    state["entry_price"] = None
    state["entry_count"] = 0
    state["last_color"] = None
    state["color_count"] = 0

def update_entry(side, entry_price):
    state["side"] = side
    state["entry_price"] = entry_price
    state["entry_count"] += 1
    state["last_color"] = None
    state["color_count"] = 0

def update_heikin_color(current_color):
    if current_color == state["last_color"]:
        state["color_count"] += 1
    else:
        state["last_color"] = current_color
        state["color_count"] = 1

def strategy_loop(interval=60):
    while True:
        try:
            price = get_market_price()
            pos_size = get_position_size()
            if pos_size == 0:
                reset_state()
                time.sleep(interval)
                continue

            current_color = "green" if price > state["entry_price"] else "red"
            update_heikin_color(current_color)

            if state["color_count"] >= 5 and current_color != state["last_color"]:
                profit_condition = (
                    (state["side"] == "buy" and price > state["entry_price"]) or
                    (state["side"] == "sell" and price < state["entry_price"])
                )
                if profit_condition:
                    print("[🎯 전략 익절 조건 충족 → 절반 청산]")
                    place_order("sell" if state["side"] == "buy" else "buy", pos_size / 2, reduce_only=True)
                    state["entry_price"] = price
                    state["entry_count"] += 1

        except Exception as e:
            print(f"[ERROR] 전략 로직 오류: {e}")
        time.sleep(interval)
