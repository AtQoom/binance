from flask import Flask, request, jsonify
import threading
import time

# ✅ gateio_api에서 필요한 함수/상수만 가져옴
from gateio_api import (
    get_equity,
    get_market_price,
    place_order,
    set_leverage,
    SYMBOL,
    RISK_PCT,
    LEVERAGE,
    MIN_QTY
)

app = Flask(__name__)

# 포지션 상태 추적용
entry_price = None
entry_side = None

# ✅ 웹훅 수신 엔드포인트
@app.route("/", methods=["POST"])
def webhook():
    global entry_price, entry_side
    try:
        data = request.get_json(force=True)
        signal = data.get("signal", "").upper()
        strength = float(data.get("strength", 1.0))

        print(f"[📨 웹훅 수신] {signal} | 강도: {strength}")

        # 포지션 반대 방향 청산 후 진입
        if "ENTRY LONG" in signal:
            place_order("sell", 0, reduce_only=True)
            side = "buy"
        elif "ENTRY SHORT" in signal:
            place_order("buy", 0, reduce_only=True)
            side = "sell"
        else:
            return jsonify({"error": "Invalid signal"}), 400

        # 진입 수량 계산
        equity = get_equity()
        price = get_market_price()
        if equity == 0 or price == 0:
            return jsonify({"error": "잔고 또는 시세 오류"}), 500

        qty = max(int((equity * RISK_PCT * LEVERAGE * strength) / price), MIN_QTY)
        place_order(side, qty)

        # 포지션 추적 업데이트
        entry_price = price
        entry_side = side

        return jsonify({"status": "주문 전송", "side": side, "qty": qty})
    except Exception as e:
        print(f"[ERROR] 웹훅 처리 실패: {e}")
        return jsonify({"error": "internal error"}), 500

# ✅ TP/SL 체크 루프 (선택적)
def check_tp_sl_loop(interval=3):
    global entry_price, entry_side
    while True:
        try:
            if entry_price and entry_side:
                price = get_market_price()
                if price:
                    if entry_side == "buy":
                        if price >= entry_price * 1.01:
                            print("[✅ TP 도달] 롱 청산")
                            place_order("sell", 0, reduce_only=True)
                            entry_price = None
                        elif price <= entry_price * 0.985:
                            print("[🛑 SL 도달] 롱 청산")
                            place_order("sell", 0, reduce_only=True)
                            entry_price = None
                    elif entry_side == "sell":
                        if price <= entry_price * 0.99:
                            print("[✅ TP 도달] 숏 청산")
                            place_order("buy", 0, reduce_only=True)
                            entry_price = None
                        elif price >= entry_price * 1.015:
                            print("[🛑 SL 도달] 숏 청산")
                            place_order("buy", 0, reduce_only=True)
                            entry_price = None
        except Exception as e:
            print(f"[ERROR] TP/SL 루프 오류: {e}")
        time.sleep(interval)

# ✅ 서버 실행부
if __name__ == "__main__":
    set_leverage()  # 시작 시 레버리지 13배로 설정
    threading.Thread(target=check_tp_sl_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
