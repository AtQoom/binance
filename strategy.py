import time
from gateio_api import get_market_price, place_order, get_equity, get_position_size
from config import SYMBOL, RISK_PCT, LEVERAGE, MIN_QTY

# 🧠 상태 저장용 딕셔너리
state = {
    "side": None,
    "entry_price": None,
    "entry_count": 0,
    "last_color": None,
    "color_count": 0
}

# ✅ 상태 초기화
def reset_state():
    state["side"] = None
    state["entry_price"] = None
    state["entry_count"] = 0
    state["last_color"] = None
    state["color_count"] = 0

# ✅ 진입 시 상태 갱신
def update_entry(side, entry_price):
    state["side"] = side
    state["entry_price"] = entry_price
    state["entry_count"] += 1
    state["last_color"] = None
    state["color_count"] = 0

# ✅ 웹훅 신호 수신 시 처리 함수
def handle_signal(signal, strength):
    print(f"[📊 전략 처리] {signal=} {strength=}")

    # 🔁 반대 포지션 정리
    if "ENTRY LONG" in signal:
        place_order("sell", 0, reduce_only=True)
        side = "buy"
    elif "ENTRY SHORT" in signal:
        place_order("buy", 0, reduce_only=True)
        side = "sell"
    else:
        print("[❌ 오류] 잘못된 시그널")
        return {"error": "Invalid signal"}

    # 💰 가용 시드 & 시세 확인
    equity = get_equity()
    price = get_market_price()
    print(f"[DEBUG] 잔고: {equity}, 시세: {price}")

    if equity == 0 or price == 0:
        print("[❌ 주문 불가] 잔고 또는 시세 오류")
        return {"error": "잔고 또는 시세 오류"}

    # 📦 주문 수량 계산
    qty = max(int((equity * RISK_PCT * LEVERAGE * strength) / price), MIN_QTY)
    print(f"[🧮 주문 준비] 방향: {side}, 수량: {qty}, 잔고: {equity:.2f}, 시세: {price:.2f}")

    # 🚀 주문 실행
    success = place_order(side, qty)
    if success:
        update_entry(side, price)
        return {"status": "주문 전송 완료", "side": side, "qty": qty}
    else:
        return {"error": "주문 실패"}

# ✅ 전략 루프 (향후 자동 청산, 추가 진입 등 구현 예정 시 사용)
def strategy_loop():
    while True:
        print("[🔄 전략 루프 실행 중...]")
        time.sleep(60)
