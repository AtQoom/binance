# core/strategy.py
import requests
import pandas as pd
from config.constants import RSI_PERIOD

class Strategy:
    def __init__(self):
        self.api_url = "https://api.gateio.ws/api/v4/futures/usdt/candlesticks"
        self.symbol = "BTC_USDT"
        self.interval = "1m"

    def get_candles(self, limit=100):
        params = {
            "contract": self.symbol,
            "interval": self.interval,
            "limit": limit
        }
        response = requests.get(self.api_url, params=params)
        data = response.json()
        df = pd.DataFrame(data, columns=['timestamp', 'volume', 'close', 'high', 'low', 'open'])
        df = df.astype(float)
        return df

    async def get_current_price(self):
        df = self.get_candles(limit=2)
        return df['close'].iloc[-1]

    async def get_current_rsi(self):
        df = self.get_candles(limit=RSI_PERIOD + 1)
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.rolling(window=RSI_PERIOD).mean()
        avg_loss = loss.rolling(window=RSI_PERIOD).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi.iloc[-1]

    async def detect_reverse_signal(self, is_long_position):
        rsi = await self.get_current_rsi()
        if is_long_position and rsi < 50:
            return True
        if not is_long_position and rsi > 50:
            return True
        return False
