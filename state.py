import json
import os

STATE_FILE = "state.json"

def init_state():
    if not os.path.exists(STATE_FILE):
        save_state({
            "side": None,
            "entry_price": 0,
            "entry_time": None,
            "qty": 0,
            "partial_exit_count": 0,
            "entry_round": 0
        })

def load_state():
    with open(STATE_FILE, 'r') as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)