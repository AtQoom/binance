# main.py

from fastapi import FastAPI
from services.ticker_listener import listen_ticker

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "GateIO Trading Server Running!"}

@app.on_event("startup")
async def startup_event():
    listen_ticker()
