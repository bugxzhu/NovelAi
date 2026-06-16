from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health, projects, world, lore, characters, chapters, llm
from app.memory.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="NovelAI", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router, prefix="/api")
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    app.include_router(world.router, prefix="/api/projects", tags=["world"])
    app.include_router(lore.router, prefix="/api/lore", tags=["lore"])
    app.include_router(characters.router, prefix="/api/characters", tags=["characters"])
    app.include_router(chapters.router, prefix="/api/chapters", tags=["chapters"])
    app.include_router(llm.router, prefix="/api/llm", tags=["llm"])
    return app


app = create_app()
