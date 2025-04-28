# core/position_manager.py

class PositionManager:
    def __init__(self):
        self.position_size = 0
        self.avg_entry_price = 0
        self.entry_count = 0

    def update_position(self, entry_price, quantity):
        total_cost = self.avg_entry_price * self.position_size
        new_cost = entry_price * quantity
        self.position_size += quantity
        self.avg_entry_price = (total_cost + new_cost) / self.position_size
        self.entry_count += 1

    def reset_position(self):
        self.position_size = 0
        self.avg_entry_price = 0
        self.entry_count = 0

    def is_in_position(self):
        return self.position_size > 0
