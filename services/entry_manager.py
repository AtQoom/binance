# services/entry_manager.py

from core.trader import place_order
from config.constants import LEVERAGE

class EntryManager:
    def __init__(self, position_manager, strategy):
        self.position_manager = position_manager
        self.strategy = strategy

    async def check_entry(self, price, rsi):
        print(f"[EntryManager] Checking entry... price={price}, rsi={rsi}")

        if rsi < 30:  # 롱 진입 조건 (간단히 예시)
            print("[EntryManager] Long Entry Signal!")
            self.position_manager.update_position(price, 1)
            place_order("buy", 1, LEVERAGE)

        elif rsi > 70:  # 숏 진입 조건 (간단히 예시)
            print("[EntryManager] Short Entry Signal!")
            self.position_manager.update_position(price, -1)
            place_order("sell", 1, LEVERAGE)
