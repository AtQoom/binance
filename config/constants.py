# config/constants.py

# 기본 거래 설정
SYMBOL = "BTC_USDT"         # 비트코인 선물
LEVERAGE = 20               # 레버리지 20배

# 기본 진입 수량 (시드 대비 퍼센트)
ENTRY_PERCENT = 10          # 기본 진입 10%
HEAVY_ENTRY_PERCENT = 20    # 강한 진입 20%

# 청산 관련 설정
FIRST_TAKE_PROFIT = 0.003    # 0.3% 수익 청산
SECOND_TAKE_PROFIT_RSI_LONG = 70  # 롱 포지션 RSI 청산
SECOND_TAKE_PROFIT_RSI_SHORT = 30 # 숏 포지션 RSI 청산

# RSI 기준
RSI_PERIOD = 14
RSI_LONG_ENTRY = 24
RSI_SHORT_ENTRY = 76
RSI_HEAVY_LONG = 17
RSI_HEAVY_SHORT = 83
