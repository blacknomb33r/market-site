# api/ping.py
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()

@app.get("/")
def ping():
    return JSONResponse({"ok": True})