# main.py
from fastapi import FastAPI
import asyncio
from services.ticker_listener import listen_ticker

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "GateIO Trading Server Running!"}

@app.on_event("startup")
async def startup_event():
    loop = asyncio.get_event_loop()
    loop.create_task(listen_ticker())  # 명시적으로 비동기 루프에 task 등록
