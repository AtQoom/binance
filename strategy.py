import time
from gateio_api import (
    get_market_price,
    get_equity,
    get_position_size,
    place_order,
    SYMBOL,
    RISK_PCT,
    LEVERAGE,
    MIN_QTY
)

# ✅ 전략 신호 처리 함수 (웹훅에서 호출됨)
def handle_signal(signal, strength):
    print(f"[📊 전략 처리] signal='{signal}' strength={strength}")
    
    side = None
    if "ENTRY LONG" in signal:
        side = "buy"
    elif "ENTRY SHORT" in signal:
        side = "sell"
    else:
        return {"error": "Invalid signal"}

    equity = get_equity()
    price = get_market_price()

    if equity == 0 or price == 0:
        print("[⚠️ 오류] 잔고 또는 시세 조회 실패")
        return {"error": "잔고 또는 시세 오류"}

    qty = max(int((equity * RISK_PCT * LEVERAGE * strength) / price), MIN_QTY)

    print(f"[🛠️ 주문 준비] 방향: {side}, 수량: {qty}, 잔고: {equity:.2f}, 시세: {price:.2f}")
    place_order(side, qty)

    return {
        "status": "주문 전송",
        "side": side,
        "qty": qty
    }

# ✅ 전략 조건 체크 루프 (익절/손절 판단 등)
def strategy_loop(interval=60):
    while True:
        try:
            print("[🔁 전략 루프] 실행 중...")

            # 포지션 없는 경우 패스
            pos_size = get_position_size()
            if pos_size == 0:
                print("[📭 포지션 없음] 루프 대기")
                time.sleep(interval)
                continue

            # 이곳에 익절/손절 등 조건 전략 넣을 수 있음
            # 예: TP 도달 시 자동 절반 청산 등

        except Exception as e:
            print(f"[ERROR] 전략 루프 오류: {e}")

        time.sleep(interval)
