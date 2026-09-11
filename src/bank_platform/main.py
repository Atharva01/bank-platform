from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from bank_platform.graph import run

app = FastAPI()

# Dev-permissive for now — no frontend origin decided yet. Tighten
# allow_origins to specific hosts before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/")
async def home():
    return {"message": "Welcome home!"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    reply = run(request.message)
    return ChatResponse(reply=reply)
