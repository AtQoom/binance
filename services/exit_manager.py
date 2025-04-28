# services/exit_manager.py

from core.trader import place_order
from config.constants import LEVERAGE

class ExitManager:
    def __init__(self, position_manager, strategy):
        self.position_manager = position_manager
        self.strategy = strategy

    async def check_exit(self, price, rsi):
        if self.position_manager.is_long_position():
            # 1차 청산: 0.3% 수익 + 40% 청산
            if self.strategy.should_take_first_profit(price, self.position_manager.avg_entry_price, True):
                qty = self.position_manager.position_size * 0.4
                place_order("sell", qty, LEVERAGE)
                self.position_manager.reduce_position(qty)
            # 2차 청산: RSI 70 도달 + 30% 청산
            elif self.strategy.should_take_second_profit(rsi, True):
                qty = self.position_manager.position_size * 0.3
                place_order("sell", qty, LEVERAGE)
                self.position_manager.reduce_position(qty)

        elif self.position_manager.is_short_position():
            # 1차 청산: 0.3% 수익 + 40% 청산
            if self.strategy.should_take_first_profit(price, self.position_manager.avg_entry_price, False):
                qty = self.position_manager.position_size * 0.4
                place_order("buy", qty, LEVERAGE)
                self.position_manager.reduce_position(qty)
            # 2차 청산: RSI 30 도달 + 30% 청산
            elif self.strategy.should_take_second_profit(rsi, False):
                qty = self.position_manager.position_size * 0.3
                place_order("buy", qty, LEVERAGE)
                self.position_manager.reduce_position(qty)

    async def check_final_exit(self, price, rsi):
        if self.position_manager.is_long_position():
            if self.strategy.is_opposite_signal(rsi, True):
                await self.exit_long_all()
        elif self.position_manager.is_short_position():
            if self.strategy.is_opposite_signal(rsi, False):
                await self.exit_short_all()

    async def exit_long_all(self):
        place_order("sell", self.position_manager.position_size, LEVERAGE)
        self.position_manager.reset_position()

    async def exit_short_all(self):
        place_order("buy", self.position_manager.position_size, LEVERAGE)
        self.position_manager.reset_position()
