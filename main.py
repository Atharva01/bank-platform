from fastapi import FastAPI

from agents import AgentRequest, AgentResponse
from coordinator import Coordinator

app = FastAPI()
coordinator = Coordinator()

@app.get("/")
async def home():
    return {"message": "Welcome home!"}

@app.post("/chat", response_model=AgentResponse)
async def chat(request: AgentRequest):
    return coordinator.route(request)
