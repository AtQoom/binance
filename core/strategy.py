# core/strategy.py

class Strategy:
    def __init__(self):
        pass

    async def get_current_price(self):
        # 실제 API 연결 전 임시 가격
        return 30000  # 예: 비트코인 가격 30000 달러로 고정

    async def get_current_rsi(self):
        # 실제 API 연결 전 임시 RSI
        return 50  # 예: RSI 50으로 고정

    async def is_reverse_signal(self, rsi, is_long):
        # 간단히 반대 신호 감지 로직 (예시)
        if is_long:
            return rsi < 50
        else:
            return rsi > 50
