# core/strategy.py

import random
import asyncio

class Strategy:
    async def get_current_price(self):
        await asyncio.sleep(0.1)  # 살짝 딜레이 (리얼틱처럼 보이게)
        return random.uniform(60000, 62000)  # BTC USDT 예시 가격 범위

    async def get_current_rsi(self):
        await asyncio.sleep(0.1)
        return random.uniform(10, 90)  # RSI 10~90 사이 랜덤 값
