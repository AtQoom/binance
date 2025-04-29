# main.py
from fastapi import FastAPI
from services.ticker_listener import listen_ticker
import asyncio

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "GateIO Trading Server Running!"}

@app.on_event("startup")
async def app_startup():
    print("Starting ticker listener...")
    asyncio.create_task(listen_ticker())
