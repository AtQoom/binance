import requests
import pandas as pd

def fetch_ohlcv(symbol="SOL_USDT", interval="1m", limit=100):
    url = f"https://api.gateio.ws/api/v4/futures/usdt/candlesticks"
    params = {
        "contract": symbol,
        "interval": interval,
        "limit": limit
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            df = pd.DataFrame(data, columns=["timestamp", "volume", "close", "high", "low", "open"])
            df = df[["timestamp", "open", "high", "low", "close", "volume"]].astype(float)
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit='s')
            return df
        else:
            print(f"[❌ OHLCV 요청 실패] {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[ERROR] OHLCV 요청 예외: {e}")
    return pd.DataFrame()

def compute_heikin_ashi(df):
    ha_df = df.copy()
    ha_df["HA_close"] = (df["open"] + df["high"] + df["low"] + df["close"]) / 4
    ha_open = [(df["open"][0] + df["close"][0]) / 2]
    for i in range(1, len(df)):
        ha_open.append((ha_open[i-1] + ha_df["HA_close"][i-1]) / 2)
    ha_df["HA_open"] = ha_open
    ha_df["HA_high"] = pd.concat([df["high"], ha_df["HA_open"], ha_df["HA_close"]], axis=1).max(axis=1)
    ha_df["HA_low"] = pd.concat([df["low"], ha_df["HA_open"], ha_df["HA_close"]], axis=1).min(axis=1)
    ha_df["HA_color"] = ha_df["HA_close"] > ha_df["HA_open"]
    return ha_df

# ✅ 추천: OHLCV 받아오고 Heikin-Ashi까지 한 번에 처리
def get_heikin_ashi_data(symbol="SOL_USDT", interval="1m", limit=100):
    df = fetch_ohlcv(symbol, interval, limit)
    if df.empty:
        return None
    return compute_heikin_ashi(df)
