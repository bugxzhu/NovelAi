"""Genre templates endpoint — read-only, returns template data for frontend."""
from fastapi import APIRouter

from app.config.genre_templates import get_genre_templates_for_api

router = APIRouter()


@router.get("")
def list_genre_templates():
    return get_genre_templates_for_api()
