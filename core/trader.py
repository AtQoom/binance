# core/trader.py

import requests
from config.settings import API_KEY, API_SECRET
from config.constants import SYMBOL

# 이건 Gate.io 실제 API 연동 부분이야 (샘플 포맷)

def place_order(side, quantity, leverage):
    print(f"Placing {side} order: {quantity} contracts with {leverage}x leverage on {SYMBOL}")
    # 여기에 실제 Gate.io API 호출 코드를 넣으면 돼
    # 이 버전은 테스트용이야

def get_current_price():
    # 예시로 그냥 1초 지연 없이 리턴
    return 50000  # 임시 비트코인 가격 (Gate.io 실시간 가격 API로 교체 가능)

def get_balance():
    # 잔고 조회 (GateIO API 연결 필요)
    return 1000  # 임시 시드

def get_position_info():
    # 현재 포지션 조회 (GateIO API 연결 필요)
    return {
        "size": 0,
        "avg_entry_price": 0
    }
