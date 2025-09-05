from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import os

app = FastAPI(title="Minimal Test API", version="0.1.0")

class TestRequest(BaseModel):
    text: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/test")
def test_endpoint(req: TestRequest):
    return {"received": req.text, "length": len(req.text)}
