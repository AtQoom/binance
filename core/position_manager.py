current_position = None  # "long", "short", None

def set_position(position):
    global current_position
    current_position = position

def get_position():
    return current_position
