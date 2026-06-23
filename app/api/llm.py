from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config.settings import settings
from app.llm.base import LLMRequest
from app.llm.router import default_router

router = APIRouter()


def _mask(key: str | None) -> str:
    """Mask an API key for safe display: keeps first 4 + last 4 chars."""
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return key[:4] + "***" + key[-4:]


@router.get("/settings")
def get_llm_settings():
    """Return current LLM configuration. API keys are masked, never raw."""
    return {
        "provider": settings.llm_provider,
        "anthropic": {
            "api_key": _mask(settings.anthropic_api_key),
            "base_url": settings.anthropic_base_url or "",
            "model": settings.anthropic_model,
        },
        "openai": {
            "api_key": _mask(settings.openai_api_key),
            "base_url": settings.openai_base_url or "",
            "model": settings.openai_model,
        },
        "embedding": {
            "model": settings.embedding_model,
            "dimensions": settings.embedding_dimensions,
        },
        "retrieval": {
            "top_k": settings.retrieval_top_k,
            "threshold": settings.retrieval_threshold,
        },
    }


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
