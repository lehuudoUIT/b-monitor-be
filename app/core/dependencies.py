"""
Authentication dependencies for protecting routes.

Import and use these in your routers to add authentication.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from app.core.database import get_db
from app.core.auth import verify_token
from app.services.user_service import get_user_by_username
from app.models.models import User

# Security scheme
security = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.
    
    This can be used to protect endpoints by adding it as a dependency.
    
    Usage:
        from app.core.dependencies import get_current_user
        from app.models.models import User
        
        @router.get("/protected")
        async def protected_route(current_user: User = Depends(get_current_user)):
            return {"user": current_user.username}
    
    Raises:
        HTTPException: 401 if token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Extract token from credentials
    token = credentials.credentials
    
    # Verify and decode token
    payload = verify_token(token)
    if payload is None:
        raise credentials_exception
    
    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception
    
    # Get user from database
    user = await get_user_by_username(db, username)
    if user is None:
        raise credentials_exception
    
    return user


# Annotated type for easier use in route handlers
CurrentUser = Annotated[User, Depends(get_current_user)]
