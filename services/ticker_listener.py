# services/ticker_listener.py

import asyncio
from services.entry_manager import EntryManager
from services.exit_manager import ExitManager
from core.position_manager import PositionManager
from core.strategy import Strategy

async def listen_ticker():
    position_manager = PositionManager()
    strategy = Strategy()
    entry_manager = EntryManager(position_manager, strategy)
    exit_manager = ExitManager(position_manager, strategy)

    while True:
        try:
            # 원래 서버 흐름
            current_price = await strategy.get_current_price()
            current_rsi = await strategy.get_current_rsi()

            # 👉 테스트용 (현재가져온 값 대신 강제 입력)
            current_rsi = 20  # 예: RSI 20으로 테스트할 때 (나중에 지워야 함)

            # 포지션 상태에 따라 진입/청산 체크
            if not position_manager.is_in_position():
                await entry_manager.check_entry(current_price, current_rsi)
            else:
                await exit_manager.check_exit(current_price, current_rsi)

            await asyncio.sleep(1)  # 1초마다 반복
        except Exception as e:
            print(f"Error in listen_ticker: {e}")
            await asyncio.sleep(5)
