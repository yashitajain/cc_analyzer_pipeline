"""
Analytics endpoints for spending insights and analysis.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db_session
from models_pydantic import StandardResponse
from services_analytics import (
    get_spending_trends,
    detect_anomalies,
    detect_recurring,
    get_summary,
)


router = APIRouter(prefix="/api/analytics", tags=["analytics"])


async def get_current_user(db: AsyncSession = Depends(None)):
    """Placeholder for current user. In real app, get from JWT token."""
    # TODO: Implement JWT token validation
    # For now, return user_id=1 (testing)
    return 1


@router.get("/trends", response_model=StandardResponse)
async def get_trends(
    months: int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db_session),
    user_id: int = Depends(get_current_user),
):
    """
    Get monthly spending trends by category.

    Args:
        months: Number of months to analyze (1-24, default 6)
        db: Database session
        user_id: Current user ID

    Returns:
        Monthly spending breakdown by category
    """

    result = await get_spending_trends(db, user_id, months)

    return StandardResponse(
        success=True,
        data=result
    )


@router.get("/anomalies", response_model=StandardResponse)
async def get_anomalies(
    threshold: float = Query(2.0, ge=0.5, le=5.0),
    db: AsyncSession = Depends(get_db_session),
    user_id: int = Depends(get_current_user),
):
    """
    Detect unusual transactions (outliers).

    Uses statistical analysis: transactions beyond mean + (std_dev * threshold) are flagged.

    Args:
        threshold: Standard deviation multiplier (0.5-5.0, default 2.0)
            - Lower = more sensitive (more anomalies)
            - Higher = less sensitive (fewer anomalies)
        db: Database session
        user_id: Current user ID

    Returns:
        List of anomalous transactions with statistical context
    """

    result = await detect_anomalies(db, user_id, threshold)

    return StandardResponse(
        success=True,
        data=result
    )


@router.get("/recurring", response_model=StandardResponse)
async def get_recurring(
    min_occurrences: int = Query(3, ge=2, le=100),
    db: AsyncSession = Depends(get_db_session),
    user_id: int = Depends(get_current_user),
):
    """
    Detect recurring transactions (subscriptions, regular purchases).

    Args:
        min_occurrences: Minimum times transaction repeats (2-100, default 3)
        db: Database session
        user_id: Current user ID

    Returns:
        List of recurring merchants with frequency and totals
    """

    result = await detect_recurring(db, user_id, min_occurrences)

    return StandardResponse(
        success=True,
        data=result
    )


@router.get("/summary", response_model=StandardResponse)
async def get_analytics_summary(
    db: AsyncSession = Depends(get_db_session),
    user_id: int = Depends(get_current_user),
):
    """
    Get summary statistics across all transactions.

    Returns:
        - Total transactions
        - Total spent (charges only)
        - Total credits (refunds)
        - Average transaction amount
        - Net amount (spent - credits)
        - Top spending category
    """

    result = await get_summary(db, user_id)

    return StandardResponse(
        success=True,
        data=result
    )
