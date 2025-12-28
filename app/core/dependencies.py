"""
Authentication dependencies for protecting routes.

Import and use these in your routers to add authentication.
"""

from fastapi import Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated, Optional

from app.core.database import get_db
from app.core.auth import verify_token
from app.services.user_service import get_user_by_username
from app.models.models import User

# Security scheme (auto_error=False allows optional bearer token)
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    db: AsyncSession = Depends(get_db),
    token_param: Optional[str] = Query(None, alias="token")
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.
    
    This can be used to protect endpoints by adding it as a dependency.
    Token can be provided either via:
    - Authorization header: Bearer <token>
    - Query parameter: ?token=<token>
    
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
    
    # Extract token from credentials (Bearer header) or query parameter
    token = None
    if credentials:
        token = credentials.credentials
    elif token_param:
        token = token_param
    
    if not token:
        raise credentials_exception
    
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
