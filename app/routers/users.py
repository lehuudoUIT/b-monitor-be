from fastapi import APIRouter
from typing import Annotated

from app.schemas.schemas import UserResponse
from app.core.dependencies import CurrentUser

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: CurrentUser):
    """
    Get current authenticated user information.
    
    This is a protected route that requires a valid JWT token in the Authorization header.
    
    Headers:
    - **Authorization**: Bearer {your_access_token}
    """
    return current_user
