"""
Transaction endpoints for listing, filtering, and managing transactions.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from datetime import datetime, date
from typing import Optional

from database import get_db_session
from db_models import User, Transaction
from models_pydantic import StandardResponse


router = APIRouter(prefix="/api/transactions", tags=["transactions"])


async def get_current_user(db: AsyncSession = Depends(None)):
    """Placeholder for current user. In real app, get from JWT token."""
    # TODO: Implement JWT token validation
    # For now, return user_id=1 (testing)
    return 1


@router.get("/", response_model=StandardResponse)
async def list_transactions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
    user_id: int = Depends(get_current_user),
):
    """
    List user's transactions with optional filtering.

    Args:
        skip: Pagination offset
        limit: Pagination limit (max 100)
        start_date: Filter by start date (YYYY-MM-DD)
        end_date: Filter by end date (YYYY-MM-DD)
        category: Filter by category
        db: Database session
        user_id: Current user ID

    Returns:
        List of transactions
    """

    # Build query
    query = select(Transaction).where(Transaction.user_id == user_id)

    # Apply filters
    filters = []

    if start_date:
        filters.append(Transaction.date >= start_date)

    if end_date:
        filters.append(Transaction.date <= end_date)

    if category:
        filters.append(Transaction.category_name == category)

    if filters:
        query = query.where(and_(*filters))

    # Order by date descending (newest first)
    query = query.order_by(desc(Transaction.date))

    # Pagination
    query = query.offset(skip).limit(limit)

    # Execute
    result = await db.execute(query)
    transactions = result.scalars().all()

    return StandardResponse(
        success=True,
        data={
            "transactions": [
                {
                    "id": t.id,
                    "date": t.date.isoformat(),
                    "merchant_name": t.merchant_name,
                    "category": t.category_name,
                    "amount": float(t.amount),
                    "is_credit": t.is_credit,
                    "source_file": t.source_file,
                }
                for t in transactions
            ],
            "count": len(transactions),
        }
    )


@router.get("/categories", response_model=StandardResponse)
async def get_categories(
    db: AsyncSession = Depends(get_db_session),
    user_id: int = Depends(get_current_user),
):
    """
    Get all transaction categories for user.

    Returns:
        List of unique categories and counts
    """

    query = select(
        Transaction.category_name
    ).where(
        Transaction.user_id == user_id
    ).distinct()

    result = await db.execute(query)
    categories = result.scalars().all()

    # Count per category
    category_counts = {}
    for category in categories:
        count_query = select(Transaction).where(
            and_(
                Transaction.user_id == user_id,
                Transaction.category_name == category
            )
        )
        count_result = await db.execute(count_query)
        category_counts[category] = len(count_result.scalars().all())

    return StandardResponse(
        success=True,
        data={
            "categories": category_counts,
        }
    )


@router.get("/{transaction_id}", response_model=StandardResponse)
async def get_transaction(
    transaction_id: int,
    db: AsyncSession = Depends(get_db_session),
    user_id: int = Depends(get_current_user),
):
    """
    Get a single transaction by ID.

    Args:
        transaction_id: Transaction ID
        db: Database session
        user_id: Current user ID

    Returns:
        Transaction details
    """

    query = select(Transaction).where(
        and_(
            Transaction.id == transaction_id,
            Transaction.user_id == user_id
        )
    )

    result = await db.execute(query)
    transaction = result.scalar()

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found"
        )

    return StandardResponse(
        success=True,
        data={
            "id": transaction.id,
            "date": transaction.date.isoformat(),
            "merchant_name": transaction.merchant_name,
            "category": transaction.category_name,
            "amount": float(transaction.amount),
            "is_credit": transaction.is_credit,
            "source_file": transaction.source_file,
            "created_at": transaction.created_at.isoformat(),
        }
    )


@router.delete("/{transaction_id}", response_model=StandardResponse)
async def delete_transaction(
    transaction_id: int,
    db: AsyncSession = Depends(get_db_session),
    user_id: int = Depends(get_current_user),
):
    """
    Delete a transaction by ID.

    Args:
        transaction_id: Transaction ID
        db: Database session
        user_id: Current user ID

    Returns:
        Success message
    """

    query = select(Transaction).where(
        and_(
            Transaction.id == transaction_id,
            Transaction.user_id == user_id
        )
    )

    result = await db.execute(query)
    transaction = result.scalar()

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found"
        )

    await db.delete(transaction)
    await db.commit()

    return StandardResponse(
        success=True,
        data={"message": "Transaction deleted"}
    )
