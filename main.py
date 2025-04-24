from flask import Flask, request, jsonify
import threading
import time
from strategy import handle_signal, strategy_loop
from state import init_state

app = Flask(__name__)
init_state()

@app.route("/", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        signal = data.get("signal", "").upper()
        strength = float(data.get("strength", 1.0))
        print(f"[📨 웹훅 수신] {signal} | 강도: {strength}")
        result = handle_signal(signal, strength)
        return jsonify(result)
    except Exception as e:
        print(f"[ERROR] 웹훅 처리 실패: {e}")
        return jsonify({"error": "internal error"}), 500

# ✅ 1. 먼저 set_leverage 함수 정의 (최상단 또는 다른 함수들과 같이)

def set_leverage(leverage=13):
    endpoint = f"/futures/usdt/positions/{SYMBOL}/leverage"
    body = safe_json_dumps({
        "leverage": leverage,
        "cross_leverage_limit": 0
    })
    timestamp = get_server_timestamp()
    headers = get_headers("POST", endpoint, timestamp, body=body)
    try:
        r = requests.post(BASE_URL + endpoint, headers=headers, data=body, timeout=10)
        print("[📌 레버리지 설정 응답]", r.status_code, r.text)
    except Exception as e:
        print("[❌ 레버리지 설정 실패]", e)

# ✅ 2. 그 아래쪽에 호출 위치 있어야 함

if __name__ == "__main__":
    set_leverage(leverage=13)  # 🔥 이게 함수 정의보다 아래에 위치해야 오류 없음!
    threading.Thread(target=check_tp_sl_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
