from flask import Flask, request, jsonify
import threading
from strategy import handle_signal
from state import init_state

app = Flask(__name__)
init_state()  # state.json 초기화

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)