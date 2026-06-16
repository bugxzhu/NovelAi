from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.llm.base import LLMRequest
from app.llm.router import default_router

router = APIRouter()


class PingRequest(BaseModel):
    prompt: str
    model_task: str = "writer_short"


class PingResponse(BaseModel):
    text: str
    input_tokens: int
    output_tokens: int


@router.post("/ping", response_model=PingResponse)
def ping(payload: PingRequest):
    try:
        resp = default_router.complete(
            LLMRequest(model_task=payload.model_task, user=payload.prompt, max_tokens=64)
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"llm call failed: {e}")
    return PingResponse(
        text=resp.text,
        input_tokens=resp.input_tokens,
        output_tokens=resp.output_tokens,
    )
