# main.py

from fastapi import FastAPI
from services.entry_manager import enter_position
from services.exit_manager import exit_partial, exit_all
from core.position_manager import get_position
from core.strategy import check_entry_signal, check_exit_signal

app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "GateIO Final Server Ready!"}

# 이후에 Webhook용 POST 엔드포인트 추가 예정
