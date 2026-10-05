from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.core.security import get_optional_user
from app.db.session import get_session
from app.schemas.errors import error_responses
from app.schemas.menu import BarMenuResponse
from app.services.bar_menu import get_bar_menu

router = APIRouter(prefix="/api/bars", tags=["bars"])


@router.get(
    "/{barId}/menu",
    response_model=BarMenuResponse,
    summary="Bar info and its current published menu",
    description=(
        "Used by the customer bar detail screen and by operators.\n\n"
        "- Public for active bars; no token is needed.\n"
        "- Inactive bars are returned only to operators. Anonymous callers and customers get "
        "`404 BAR_NOT_FOUND`, the same as for a missing bar.\n"
        "- A bar without a published menu returns `200` with `menuBoardId: null` and `items: []`.\n"
        "- Items and their options are sorted by `sortOrder`."
    ),
    responses=error_responses(
        (401, "`UNAUTHENTICATED`: an Authorization header was sent but the token is invalid or expired."),
        (404, "`BAR_NOT_FOUND`: no such bar, a malformed id, or an inactive bar for a non-operator."),
    ),
)
def read_bar_menu(
    bar_id: Annotated[str, Path(alias="barId", description="Bar id (UUID)")],
    session: Session = Depends(get_session),
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> BarMenuResponse:
    is_operator = user is not None and user.get("user_type") == "operator"
    return get_bar_menu(session, bar_id, include_inactive=is_operator)
