from services.entry_manager import EntryManager
from services.exit_manager import ExitManager
from core.position_manager import PositionManager
from core.strategy import Strategy
from config.settings import API_KEY, API_SECRET
import asyncio

# 간단한 구조
async def listen_ticker():
    # 기본 객체 생성
    position_manager = PositionManager()
    strategy = Strategy()
    entry_manager = EntryManager(position_manager, strategy)
    exit_manager = ExitManager(position_manager, strategy)

    while True:
        try:
            # 가격, rsi 등 가져오기
            price = await strategy.get_current_price()
            rsi = await strategy.get_current_rsi()

            # 포지션 유무에 따라 진입 / 청산
            if not position_manager.is_in_position():
                await entry_manager.check_entry(price, rsi)
            else:
                await exit_manager.check_exit(price, rsi)

            await asyncio.sleep(1)  # 1초마다 체크
        except Exception as e:
            print(f"Error in listen_ticker: {e}")
            await asyncio.sleep(5)
