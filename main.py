from flask import Flask, request, jsonify
import threading
import time
import json
import requests

from strategy import handle_signal, strategy_loop
from state import init_state
from gateio_api import get_server_timestamp, get_headers, BASE_URL, SYMBOL, safe_json_dumps

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

# ✅ 실행 시 13배 격리모드 설정
def set_leverage(leverage=13):
    endpoint = f"/futures/usdt/positions/{SYMBOL}/leverage"
    payload = {
        "leverage": leverage,
        "cross_leverage_limit": 0  # 0이면 격리 모드
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

# ✅ 전략 루프 실행
if __name__ == "__main__":
    set_leverage(leverage=13)  # 🔥 최초 실행 시 13배 격리 설정
    threading.Thread(target=strategy_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
