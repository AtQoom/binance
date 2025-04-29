# services/exit_manager.py

from core.trader import place_order
from config.constants import LEVERAGE

class ExitManager:
    def __init__(self, position_manager, strategy):
        self.position_manager = position_manager
        self.strategy = strategy

    async def check_exit(self, price, rsi):
        print(f"[ExitManager] Checking exit... price={price}, rsi={rsi}")

        if self.position_manager.is_in_position():
            if await self.strategy.is_reverse_signal(rsi, self.position_manager.is_long()):
                print("[ExitManager] Reverse Signal Detected! Closing position.")
                place_order("sell" if self.position_manager.is_long() else "buy", self.position_manager.position_size, LEVERAGE)
                self.position_manager.reset_position()
