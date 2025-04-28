# services/ticker_listener.py

from services.entry_manager import EntryManager
from services.exit_manager import ExitManager
from core.position_manager import PositionManager
from core.strategy import Strategy
import asyncio

async def listen_ticker():
    position_manager = PositionManager()
    strategy = Strategy()
    entry_manager = EntryManager(position_manager, strategy)
    exit_manager = ExitManager(position_manager, strategy)

    while True:
        try:
            # 가격, RSI 불러오기
            price = await strategy.get_current_price()
            rsi = await strategy.get_current_rsi()

            # 포지션 상태에 따라 진입 또는 청산
            if not position_manager.is_in_position():
                await entry_manager.check_entry(price, rsi)
            else:
                await exit_manager.check_exit(price, rsi)
                await exit_manager.check_final_exit(price, rsi)  # 3차 청산도 체크!

            await asyncio.sleep(1)
        except Exception as e:
            print(f"Error in listen_ticker: {e}")
            await asyncio.sleep(5)
