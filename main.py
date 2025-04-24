from flask import Flask, request, jsonify
import threading
import time
import requests
import json

from strategy import handle_signal, strategy_loop
from state import init_state
from gateio_api import get_headers, BASE_URL, SYMBOL, safe_json_dumps  # ✅ 이건 그대로 유지

app = Flask(__name__)
init_state()

# ✅ 서버 시간 가져오기 - 초 단위로!
def get_server_timestamp():
    try:
        r = requests.get("https://api.gateio.ws/api/v4/timestamp", timeout=5)
        if r.status_code == 200:
            return str(int(r.text))  # 초 단위
    except Exception as e:
        print("[❌ 서버 시간 조회 실패]", e)
    return str(int(time.time()))

# ✅ 레버리지 설정 (검증된 버전)
def set_leverage(leverage=13):
    endpoint = f"/futures/usdt/positions/{SYMBOL}/leverage"
    payload = {
        "leverage": leverage,
        "cross_leverage_limit": 0
    }
    timestamp = get_server_timestamp()
    headers = get_headers("POST", endpoint, timestamp, body=json.dumps(payload))

    try:
        r = requests.post(
            BASE_URL + endpoint,
            headers=headers,
            data=json.dumps(payload),
            timeout=10
        )
        print("[📌 레버리지 설정 응답]", r.status_code, r.text)
    except Exception as e:
        print("[❌ 레버리지 설정 실패]", e)

# ✅ 트레이딩뷰 웹훅 수신
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

# ✅ 실행
if __name__ == "__main__":
    set_leverage(leverage=13)  # 실행 시 레버리지 설정
    threading.Thread(target=strategy_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
