from fastapi import APIRouter

from app.deps import CurrentUser
from app.schemas import UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
