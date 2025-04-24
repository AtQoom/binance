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
        print(f"[ERROR] OHLCV 요청 에러: {e}")
    return pd.DataFrame()

def compute_heikin_ashi(df):
    ha_df = df.copy()
    ha_df["HA_close"] = (df["open"] + df["high"] + df["low"] + df["close"]) / 4
    ha_open = [(df["open"][0] + df["close"][0]) / 2]
    for i in range(1, len(df)):
        ha_open.append((ha_open[i-1] + ha_df["HA_close"][i-1]) / 2)
    ha_df["HA_open"] = ha_open
    ha_df["HA_high"] = ha_df[["high", "HA_open", "HA_close"]].max(axis=1)
    ha_df["HA_low"] = ha_df[["low", "HA_open", "HA_close"]].min(axis=1)
    ha_df["HA_color"] = ha_df["HA_close"] > ha_df["HA_open"]
    return ha_df