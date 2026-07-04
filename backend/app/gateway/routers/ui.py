"""Gateway endpoint surfacing frontend UI behavior toggles.

The toggles live in ``config.yaml`` under ``ui:`` (see ``UIConfig``). The
frontend fetches this endpoint once (TanStack Query) and adapts rendering —
e.g. ``show_tool_output`` controls whether ``bash`` tool stdout is shown in
the chat ChainOfThought, which is hidden by upstream deer-flow design but
useful for execution-style skills during debugging.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.gateway.deps import get_config
from deerflow.config.app_config import AppConfig

router = APIRouter(prefix="/api", tags=["ui"])


class UIConfigResponse(BaseModel):
    show_tool_output: bool = Field(
        ..., description="Show tool (bash) stdout in the chat UI (debug toggle)"
    )


@router.get("/ui/config", response_model=UIConfigResponse)
async def get_ui_config(
    config: AppConfig = Depends(get_config),
) -> UIConfigResponse:
    # Reads through get_config(), which hot-reloads on config.yaml changes,
    # so flipping ui.show_tool_output takes effect without a restart.
    return UIConfigResponse(show_tool_output=config.ui.show_tool_output)
