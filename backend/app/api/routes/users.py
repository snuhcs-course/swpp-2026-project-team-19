from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import Principal, get_current_user
from app.db.session import get_session
from app.schemas.errors import error_responses
from app.schemas.user import CurrentUserResponse
from app.services.users import sync_current_user

router = APIRouter(prefix="/api", tags=["users"])


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    summary="The signed-in user",
    description=(
        "Call after login and when the app starts. The first call creates the user as a customer; "
        "later calls return the same user and update the email from the token. The display name "
        "starts as the Google account name (at most 20 characters) and is not overwritten later."
    ),
    responses=error_responses(
        (401, "`UNAUTHENTICATED`: missing, invalid or expired token."),
        (503, "`SERVICE_UNAVAILABLE`: the server cannot check tokens now (settings or signing keys)."),
    ),
)
def read_current_user(
    # Declared before the session so a request without a valid token never opens a database session.
    principal: Principal = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> CurrentUserResponse:
    user = sync_current_user(session, principal)
    return CurrentUserResponse(
        userId=user.id,
        email=user.email,
        displayName=user.display_name,
        userType=user.user_type.value,
        updatedAt=user.updated_at,
    )
