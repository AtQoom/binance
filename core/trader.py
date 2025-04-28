# core/trader.py

def place_order(side, quantity, leverage):
    # 시뮬레이션 모드: 실제 주문 없이 로그만 출력
    print(f"[SIMULATION] {side.upper()} 주문 발생 - 수량: {quantity:.4f}개, 레버리지: {leverage}배")
