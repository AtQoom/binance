# services/ticker_listener.py

import asyncio
from services.entry_manager import EntryManager
from services.exit_manager import ExitManager
from core.position_manager import PositionManager
from core.strategy import Strategy

async def listen_ticker():
    print("🔵 listen_ticker started!")  # ✅ 서버 시작 확인용 로그

    position_manager = PositionManager()
    strategy = Strategy()
    entry_manager = EntryManager(position_manager, strategy)
    exit_manager = ExitManager(position_manager, strategy)

    while True:
        try:
            print("🟢 Ticker Loop Start")  # ✅ 루프 시작 확인용 로그
            current_price = await strategy.get_current_price()
            current_rsi = await strategy.get_current_rsi()

            if not position_manager.is_in_position():
                print(f"🟡 Entry Check: Price {current_price}, RSI {current_rsi}")
                await entry_manager.check_entry(current_price, current_rsi)
            else:
                print(f"🟠 Exit Check: Price {current_price}, RSI {current_rsi}")
                await exit_manager.check_exit(current_price, current_rsi)

            await asyncio.sleep(1)
        except Exception as e:
            print(f"🔴 Error in listen_ticker: {e}")
            await asyncio.sleep(5)
