# services/entry_manager.py

from core.trader import place_order
from config.constants import LEVERAGE

class EntryManager:
    def __init__(self, position_manager, strategy):
        self.position_manager = position_manager
        self.strategy = strategy

    async def check_entry(self, price, rsi):
        if self.strategy.should_enter_long(rsi):
            strong = self.strategy.is_heavy_entry_long(rsi)
            qty = self.calculate_entry_qty(price, strong)
            place_order("buy", qty, LEVERAGE)
            self.position_manager.update_position(price, qty)

        elif self.strategy.should_enter_short(rsi):
            strong = self.strategy.is_heavy_entry_short(rsi)
            qty = self.calculate_entry_qty(price, strong)
            place_order("sell", qty, LEVERAGE)
            self.position_manager.update_position(price, -qty)

    def calculate_entry_qty(self, price, strong):
        # 시드 대비 진입수량 계산
        percent = ENTRY_PERCENT if not strong else HEAVY_ENTRY_PERCENT
        # 여기선 account_balance = 1000 USD 가정 (필요시 수정)
        account_balance = 1000
        usd_amount = account_balance * percent / 100
        qty = usd_amount / price
        return qty
