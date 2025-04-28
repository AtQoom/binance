from core.trader import place_order
from config.constants import LEVERAGE

class ExitManager:
    def __init__(self, position_manager, strategy):
        self.position_manager = position_manager
        self.strategy = strategy

    async def check_exit(self, price, rsi):
        # 기존 1차, 2차 청산 로직

    async def check_final_exit(self, price, rsi):
        if self.position_manager.is_long_position():
            if self.strategy.is_opposite_signal(rsi, True):  # True = 롱
                await self.exit_long_all()
        elif self.position_manager.is_short_position():
            if self.strategy.is_opposite_signal(rsi, False):  # False = 숏
                await self.exit_short_all()

    async def exit_long_all(self):
        place_order("sell", self.position_manager.position_size, LEVERAGE)
        self.position_manager.reset_position()

    async def exit_short_all(self):
        place_order("buy", self.position_manager.position_size, LEVERAGE)
        self.position_manager.reset_position()
