from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.core.security import get_optional_user
from app.db.session import get_session
from app.schemas.menu import BarMenuResponse
from app.services.bar_menu import get_bar_menu

router = APIRouter(prefix="/api/bars", tags=["bars"])


@router.get(
    "/{barId}/menu",
    response_model=BarMenuResponse,
    summary="Bar info and its current published menu",
    description="Public for active bars. Inactive bars are visible to operators only; others get 404 BAR_NOT_FOUND.",
)
def read_bar_menu(
    bar_id: Annotated[str, Path(alias="barId")],
    session: Session = Depends(get_session),
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> BarMenuResponse:
    is_operator = user is not None and user.get("user_type") == "operator"
    return get_bar_menu(session, bar_id, include_inactive=is_operator)
