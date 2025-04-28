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
            current_price = await strategy.get_current_price()
            current_rsi = await strategy.get_current_rsi()

            print(f"[Ticker] 가격: {current_price:.2f}, RSI: {current_rsi:.2f}")

            if not position_manager.is_in_position():
                await entry_manager.check_entry(current_price, current_rsi)
            else:
                await exit_manager.check_exit(current_price, current_rsi)

            await asyncio.sleep(1)  # 1초마다 실행
        except Exception as e:
            print(f"[Error] {e}")
            await asyncio.sleep(5)
