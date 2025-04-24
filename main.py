from flask import Flask, request, jsonify
import threading
import time
from strategy import handle_signal, check_exit_condition
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

def exit_condition_loop():
    while True:
        check_exit_condition()
        time.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=exit_condition_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)