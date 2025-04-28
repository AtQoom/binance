# services/exit_manager.py
async def check_final_exit(self, price, rsi):
    if self.position_manager.is_long_position():
        if rsi < RSI_LONG_ENTRY:  # 롱포지션인데 숏 신호
            await self.exit_manager.exit_long_all()
    elif self.position_manager.is_short_position():
        if rsi > RSI_SHORT_ENTRY:  # 숏포지션인데 롱 신호
            await self.exit_manager.exit_short_all()

async def exit_long_all(self):
    # 남은 모든 롱 포지션 청산
    place_order("sell", self.position_manager.position_size, LEVERAGE)
    self.position_manager.reset_position()

async def exit_short_all(self):
    # 남은 모든 숏 포지션 청산
    place_order("buy", self.position_manager.position_size, LEVERAGE)
    self.position_manager.reset_position()
