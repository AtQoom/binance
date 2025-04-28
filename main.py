# main.py

from fastapi import FastAPI
from services.ticker_listener import listen_ticker
import asyncio

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "GateIO Trading Server Running!"}

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(listen_ticker())  # ✅ 이렇게 해야 백그라운드에서 돌면서 서버 유지
