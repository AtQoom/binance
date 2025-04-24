import json, time, requests

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
            return str(int(r.text))
    except Exception as e:
        print(f"[ERROR] 서버 시간 조회 실패: {e}")
    return str(int(time.time()))