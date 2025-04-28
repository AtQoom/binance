# config/constants.py

# 거래 설정
API_URL = "https://api.gateio.ws/api/v4"
SYMBOL = "BTC_USDT"  # 비트코인 선물 심볼
LEVERAGE = 20        # 레버리지 20배

# 청산 관련 설정
TAKE_PROFIT_PERCENT = 0.3  # 1차 청산: 평단대비 0.3% 수익
PARTIAL_CLOSE_1 = 0.4      # 1차 청산: 보유수량 40%
PARTIAL_CLOSE_2 = 0.3      # 2차 청산: 보유수량 30%

# 진입 설정
ENTRY_PERCENT_NORMAL = 0.10  # 10% 시드 진입 (기본)
ENTRY_PERCENT_STRONG = 0.20  # 20% 시드 진입 (RSI 17 이하 or 83 이상)
