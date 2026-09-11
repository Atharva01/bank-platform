from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from bank_platform.agents import AgentRequest, AgentResponse
from bank_platform.coordinator import Coordinator

app = FastAPI()

# Dev-permissive for now — no frontend origin decided yet. Tighten
# allow_origins to specific hosts before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

coordinator = Coordinator()

_ERROR_STATUS = {
    "invalid_intent": 400,
    "unknown_agent": 400,
    "unknown_operation": 400,
    "missing_field": 400,
    "validation_error": 400,
    "not_found": 404,
    "insufficient_funds": 422,
    "invalid_status_transition": 422,
}

@app.get("/")
async def home():
    return {"message": "Welcome home!"}

@app.post("/chat", response_model=AgentResponse)
async def chat(request: AgentRequest):
    response = coordinator.route(request)
    if response.success:
        return response
    status_code = _ERROR_STATUS.get(response.error, 400)
    return JSONResponse(content=response.model_dump(), status_code=status_code)
