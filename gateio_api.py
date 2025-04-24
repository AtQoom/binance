import os, time, json, hmac, hashlib, requests

API_KEY = os.environ.get("API_KEY", "")
API_SECRET = os.environ.get("API_SECRET", "")
BASE_URL = "https://api.gateio.ws/api/v4"
SYMBOL = "SOL_USDT"
MIN_ORDER_USDT = 3
MIN_QTY = 1
LEVERAGE = 6

def get_headers(method, endpoint, query="", body=""):
    timestamp = str(int(time.time() * 1000))
    full_path = f"/api/v4{endpoint}"
    hashed_payload = hashlib.sha512((body or "").encode('utf-8')).hexdigest()
    sign_str = f"{method.upper()}\n{full_path}\n{query}\n{hashed_payload}\n{timestamp}"
    sign = hmac.new(API_SECRET.encode(), sign_str.encode(), hashlib.sha512).hexdigest()
    return {
        "KEY": API_KEY, "Timestamp": timestamp, "SIGN": sign,
        "Content-Type": "application/json", "Accept": "application/json"
    }

def get_equity():
    try:
        endpoint = "/futures/usdt/accounts"
        headers = get_headers("GET", endpoint)
        r = requests.get(BASE_URL + endpoint, headers=headers, timeout=10)

        print("[DEBUG] 잔고 API 응답 상태:", r.status_code)
        print("[DEBUG] 잔고 API 응답 내용:", r.text)  # 👈 여기 중요!

        if r.status_code == 200:
            return float(r.json()["available"])
    except Exception as e:
        print(f"[ERROR] 잔고 조회 실패: {e}")
    return 0

def get_market_price():
    try:
        endpoint = "/futures/usdt/tickers"
        headers = get_headers("GET", endpoint)
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
        headers = get_headers("GET", endpoint)
        r = requests.get(BASE_URL + endpoint, headers=headers, timeout=10)
        if r.status_code == 200:
            for p in r.json():
                if p["contract"] == SYMBOL:
                    return float(p["size"])
    except Exception as e:
        print(f"[ERROR] 포지션 조회 실패: {e}")
    return 0

def place_order(side, qty, reduce_only=False):
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
    body = json.dumps({
        "contract": SYMBOL,
        "size": qty,
        "price": 0,
        "side": side,
        "tif": "ioc",
        "reduce_only": reduce_only,
        "close": reduce_only
    })
    headers = get_headers("POST", "/futures/usdt/orders", body=body)
    try:
        r = requests.post(BASE_URL + "/futures/usdt/orders", headers=headers, data=body, timeout=10)
        if r.status_code == 200:
            print(f"[🚀 주문] {side.upper()} {qty}개")
        else:
            print(f"[❌ 주문 실패] {r.status_code} - {r.text}")
    except Exception as e:
        print(f"[ERROR] 주문 실패: {e}")
