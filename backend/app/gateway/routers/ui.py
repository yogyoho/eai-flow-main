"""UI configuration endpoint (EAI minimal stub)."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v1/ui/config")
async def ui_config():
    return {"show_tool_output": False}
