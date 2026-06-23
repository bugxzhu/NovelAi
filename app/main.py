from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    chapters,
    chapters_discuss,
    chapters_finalize,
    chapters_generate,
    chapters_polish,
    chapters_review,
    characters,
    characters_states,
    deps,
    events,
    genre_templates,
    generation_logs,
    health,
    llm,
    lore,
    pending_updates,
    plot_lines,
    projects,
    relationships,
    search,
    story_milestones,
    world,
)
from app.memory.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="NovelAI", version="0.1.0", lifespan=lifespan)

    # CORS — allow the Next.js dev server (M2b)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3300",
            "http://127.0.0.1:3300",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Accel-Buffering"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    app.include_router(world.router, prefix="/api/projects", tags=["world"])
    app.include_router(lore.router, prefix="/api/lore", tags=["lore"])
    app.include_router(characters.router, prefix="/api/characters", tags=["characters"])
    app.include_router(characters_states.router, prefix="/api/characters",
                       tags=["characters"])
    app.include_router(chapters.router, prefix="/api/chapters", tags=["chapters"])
    app.include_router(chapters_generate.router, prefix="/api/chapters",
                       tags=["chapters_generate"])
    app.include_router(chapters_finalize.router, prefix="/api/chapters",
                       tags=["chapters_finalize"])
    app.include_router(chapters_review.router, prefix="/api/chapters",
                       tags=["chapters_review"])
    app.include_router(chapters_discuss.router, prefix="/api/chapters",
                       tags=["chapters_discuss"])
    app.include_router(chapters_polish.router, prefix="/api/chapters",
                       tags=["chapters_polish"])
    app.include_router(llm.router, prefix="/api/llm", tags=["llm"])
    app.include_router(generation_logs.router, prefix="/api/generation-logs",
                       tags=["generation_logs"])
    app.include_router(pending_updates.router, prefix="/api/pending-updates",
                       tags=["pending_updates"])
    app.include_router(plot_lines.router, prefix="/api/plot-lines",
                       tags=["plot_lines"])
    app.include_router(relationships.router, prefix="/api/relationships",
                       tags=["relationships"])
    app.include_router(events.router, prefix="/api/events", tags=["events"])
    app.include_router(story_milestones.router, prefix="/api/story-milestones",
                       tags=["story_milestones"])
    app.include_router(genre_templates.router, prefix="/api/genre-templates",
                       tags=["genre_templates"])
    app.include_router(search.router, prefix="/api/search", tags=["search"])
    return app


app = create_app()
