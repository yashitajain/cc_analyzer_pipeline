"""
FastAPI application entry point.
Defines routes and middleware.
"""

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import settings
from database import get_db_session, init_db, close_db
from db_models import User
from models_pydantic import (
    UserCreate, UserLogin, UserResponse, AuthToken, StandardResponse
)
from auth import hash_password, verify_password, create_jwt_token, decode_jwt_token
from redis_client import init_redis, close_redis
from api import upload

# Create app
app = FastAPI(
    title="CC Pipeline API",
    description="Credit card statement analyzer backend",
    version="2.0.0",
)

# CORS middleware (allow frontend requests)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Startup / Shutdown
# ============================================================================

@app.on_event("startup")
async def startup():
    """Initialize database and Redis on startup."""
    await init_db()
    await init_redis()


@app.on_event("shutdown")
async def shutdown():
    """Close database on shutdown."""
    await close_db()
    await close_redis()


# ============================================================================
# Auth Endpoints
# ============================================================================

@app.post("/api/auth/register", response_model=UserResponse)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Register a new user.

    Args:
        user_data: username, password, email
        db: async database session

    Returns:
        User object (without password)

    Raises:
        400: Username already exists
    """
    # Check if username exists
    stmt = select(User).where(User.username == user_data.username)
    result = await db.execute(stmt)
    if result.scalar():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )

    # Create user
    user = User(
        username=user_data.username,
        hashed_password=hash_password(user_data.password),
        email=user_data.email,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user


@app.post("/api/auth/login", response_model=AuthToken)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Login with username and password.
    Returns JWT token.

    Args:
        credentials: username, password
        db: async database session

    Returns:
        JWT token

    Raises:
        401: Invalid credentials
    """
    # Get user
    stmt = select(User).where(User.username == credentials.username)
    result = await db.execute(stmt)
    user = result.scalar()

    # Verify password
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    # Create token
    token = create_jwt_token({"user_id": user.id, "username": user.username})

    return AuthToken(
        access_token=token,
        user_id=user.id,
    )


async def get_current_user(
    authorization: str = Depends(lambda: None),
    db: AsyncSession = Depends(get_db_session)
) -> User:
    """
    Get current user from JWT token in Authorization header.
    Used in protected endpoints.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header"
        )

    # Decode token
    payload = decode_jwt_token(authorization)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    # Get user
    user_id = payload.get("user_id")
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    return user


# ============================================================================
# Health Check
# ============================================================================

@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current logged-in user."""
    return current_user

# ============================================================================
# Include Routers
# ============================================================================

app.include_router(upload.router)  

# ============================================================================
# Root
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "CC Pipeline API v2.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
