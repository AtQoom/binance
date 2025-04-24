import os, time, json, hmac, hashlib, requests
from flask import Flask, request, jsonify
from datetime import datetime
import threading

app = Flask(__name__)

# 환경 변수
API_KEY = os.environ.get("API_KEY", "")
API_SECRET = os.environ.get("API_SECRET", "")
BASE_URL = "https://api.gateio.ws/api/v4"

# 설정
SYMBOL = "SOL_USDT"
MIN_ORDER_USDT = 3
MIN_QTY = 1
LEVERAGE = 13
RISK_PCT = round(0.10 / LEVERAGE, 6)  # ✅ 총 시드의 10% 진입

entry_price = None
entry_side = None

def safe_json_dumps(obj):
    try:
        return json.dumps(obj, separators=(',', ':'), allow_nan=False)
    except Exception as e:
        print(f"[❌ JSON 직렬화 오류]: {e}")
        return ""

def get_server_timestamp():
    try:
        r = requests.get("https://api.gateio.ws/api/v4/timestamp", timeout=5)
        if r.status_code == 200:
            return str(int(r.text))  # 초 단위
    except Exception as e:
        print(f"[ERROR] 서버 시간 조회 실패: {e}")
    return str(int(time.time()))

def get_headers(method, endpoint, timestamp, query="", body=""):
    full_path = f"/api/v4{endpoint}"
    hashed_payload = hashlib.sha512((body or "").encode('utf-8')).hexdigest()
    sign_str = f"{method.upper()}\n{full_path}\n{query}\n{hashed_payload}\n{timestamp}"
    sign = hmac.new(API_SECRET.encode(), sign_str.encode(), hashlib.sha512).hexdigest()
    return {
        "KEY": API_KEY,
        "Timestamp": timestamp,
        "SIGN": sign,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

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

def get_equity():
    try:
        endpoint = "/futures/usdt/accounts"
        timestamp = get_server_timestamp()
        headers = get_headers("GET", endpoint, timestamp)
        r = requests.get(BASE_URL + endpoint, headers=headers, timeout=10)
        print("[DEBUG] 잔고 응답:", r.status_code, r.text)
        if r.status_code == 200:
            return float(r.json()["available"])
    except Exception as e:
        print(f"[ERROR] 잔고 조회 실패: {e}")
    return 0

def get_market_price():
    try:
        endpoint = "/futures/usdt/tickers"
        timestamp = get_server_timestamp()
        headers = get_headers("GET", endpoint, timestamp)
        r = requests.get(BASE_URL + endpoint, headers=headers, timeout=10)
        if r.status_code == 200:
            for t in r.json():
                if t["contract"] == SYMBOL:
                    return float(t["last"])
    except Exception as e:
        print(f"[ERROR] 시세 조회 실패: {e}")
    return 0

def get_position_size():
    try:
        endpoint = "/futures/usdt/positions"
        timestamp = get_server_timestamp()
        headers = get_headers("GET", endpoint, timestamp)
        r = requests.get(BASE_URL + endpoint, headers=headers, timeout=10)
        if r.status_code == 200:
            for p in r.json():
                if p["contract"] == SYMBOL:
                    return float(p["size"])
    except Exception as e:
        print(f"[ERROR] 포지션 조회 실패: {e}")
    return 0

def place_order(side, qty, reduce_only=False):
    global entry_price, entry_side
    price = get_market_price()
    if price == 0:
        return
    if reduce_only:
        qty = get_position_size()
        if qty <= 0:
            return
    notional = qty * price
    if notional < MIN_ORDER_USDT and not reduce_only:
        print(f"[❌ 주문 금액 {notional:.2f} < 최소 {MIN_ORDER_USDT}]")
        return
    body = safe_json_dumps({
        "contract": SYMBOL,
        "size": qty,
        "price": 0,
        "side": side,
        "tif": "ioc",
        "reduce_only": reduce_only,
        "close": reduce_only
    })
    timestamp = get_server_timestamp()
    headers = get_headers("POST", "/futures/usdt/orders", timestamp, body=body)
    try:
        r = requests.post(BASE_URL + "/futures/usdt/orders", headers=headers, data=body, timeout=10)
        if r.status_code == 200:
            print(f"[🚀 주문] {side.upper()} {qty}개")
            if not reduce_only:
                entry_price = price
                entry_side = side
        else:
            print(f"[❌ 주문 실패] {r.status_code} - {r.text}")
    except Exception as e:
        print(f"[ERROR] 주문 실패: {e}")

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
            print(f"[ERROR] TP/SL 체크 실패: {e}")
        time.sleep(interval)

@app.route("/", methods=["POST"])
def webhook():
    global entry_price, entry_side
    try:
        data = request.get_json(force=True)
        signal = data.get("signal", "")
        strength = float(data.get("strength", "1.0"))
        print(f"[📨 웹훅 수신] {signal} | 강도: {strength}")
        if "ENTRY LONG" in signal:
            place_order("sell", 0, reduce_only=True)
            side = "buy"
        elif "ENTRY SHORT" in signal:
            place_order("buy", 0, reduce_only=True)
            side = "sell"
        else:
            return jsonify({"error": "Invalid signal"}), 400

        equity = get_equity()
        price = get_market_price()
        if equity == 0 or price == 0:
            return jsonify({"error": "잔고 또는 시세 오류"}), 500

        qty = max(int((equity * RISK_PCT * LEVERAGE * strength) / price), MIN_QTY)
        place_order(side, qty)
        return jsonify({"status": "주문 전송", "side": side, "qty": qty})
    except Exception as e:
        print(f"[ERROR] 웹훅 처리 실패: {e}")
        return jsonify({"error": "internal error"}), 500

if __name__ == "__main__":
    set_leverage(leverage=LEVERAGE)
    threading.Thread(target=check_tp_sl_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
