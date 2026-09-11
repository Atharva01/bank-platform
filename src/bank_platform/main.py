from fastapi import FastAPI

from bank_platform.agents import AgentRequest, AgentResponse
from bank_platform.coordinator import Coordinator

app = FastAPI()
coordinator = Coordinator()

@app.get("/")
async def home():
    return {"message": "Welcome home!"}

@app.post("/chat", response_model=AgentResponse)
async def chat(request: AgentRequest):
    return coordinator.route(request)
