from config.constants import *
from core.position_manager import set_position

def exit_partial(current_qty, partial_ratio):
    qty_to_exit = current_qty * partial_ratio
    return qty_to_exit

def exit_all():
    set_position(None)
    return "close_all"
