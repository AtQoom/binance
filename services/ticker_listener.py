# services/ticker_listener.py

from services.entry_manager import enter_long, enter_short
from services.exit_manager import exit_long, exit_short
from core.position_manager import PositionManager
from core.strategy import *
from config.settings import API_KEY, API_SECRET
import asyncio

async def listen_ticker():
    position_manager = PositionManager()

    while True:
        try:
            # 가격과 RSI 데이터 받아오기 (Gate.io API 연결 예정)
            price = 50000  # 임시
            rsi = 40       # 임시

            # 진입/청산 체크
            if not position_manager.is_in_position():
                if should_enter_long(rsi):
                    enter_long(0.01)  # 수량은 예시
                    position_manager.update_position(price, 0.01)
                elif should_enter_short(rsi):
                    enter_short(0.01)
                    position_manager.update_position(price, 0.01)
            else:
                # 포지션 있을 때 청산 체크
                is_long = True  # 예시
                if should_take_first_profit(price, position_manager.avg_entry_price, is_long):
                    exit_long(position_manager.position_size * 0.4)

                if should_take_second_profit(rsi, is_long):
                    exit_long(position_manager.position_size * 0.3)

            await asyncio.sleep(1)

        except Exception as e:
            print(f"Error in ticker_listener: {e}")
            await asyncio.sleep(5)
