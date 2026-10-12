"""
Analytics service for spending analysis and insights.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from db_models import Transaction
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List


async def get_spending_trends(
    db: AsyncSession,
    user_id: int,
    months: int = 6,
) -> Dict:
    """
    Get monthly spending trends by category.

    Args:
        db: Database session
        user_id: User ID
        months: Number of months to analyze

    Returns:
        Dict with monthly totals by category
    """

    # Get transactions from last N months
    start_date = datetime.now().date().replace(day=1) - timedelta(days=30*months)

    query = select(Transaction).where(
        and_(
            Transaction.user_id == user_id,
            Transaction.date >= start_date
        )
    ).order_by(Transaction.date)

    result = await db.execute(query)
    transactions = result.scalars().all()

    # Group by month and category
    trends = {}
    for txn in transactions:
        month_key = txn.date.strftime("%Y-%m")

        if month_key not in trends:
            trends[month_key] = {}

        category = txn.category_name
        if category not in trends[month_key]:
            trends[month_key][category] = 0

        amount = float(txn.amount) * (-1 if not txn.is_credit else 1)
        trends[month_key][category] += amount

    return {"trends": trends}


async def detect_anomalies(
    db: AsyncSession,
    user_id: int,
    std_dev_threshold: float = 2.0,
) -> Dict:
    """
    Detect unusual transactions (outliers).

    Uses standard deviation: transactions > mean + (std_dev * threshold) are anomalies.

    Args:
        db: Database session
        user_id: User ID
        std_dev_threshold: Number of standard deviations (default 2.0)

    Returns:
        List of anomalous transactions
    """

    query = select(Transaction).where(
        and_(
            Transaction.user_id == user_id,
            Transaction.is_credit == False  # Only charges, not credits
        )
    )

    result = await db.execute(query)
    transactions = result.scalars().all()

    if not transactions:
        return {"anomalies": []}

    # Calculate mean and std dev per category
    categories = {}
    for txn in transactions:
        cat = txn.category_name
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(float(txn.amount))

    # Find anomalies
    anomalies = []
    for txn in transactions:
        cat = txn.category_name
        amounts = categories[cat]

        if len(amounts) < 3:
            continue  # Need at least 3 for statistics

        mean = sum(amounts) / len(amounts)
        variance = sum((x - mean) ** 2 for x in amounts) / len(amounts)
        std_dev = variance ** 0.5

        # Check if anomaly
        threshold = mean + (std_dev * std_dev_threshold)
        if float(txn.amount) > threshold:
            anomalies.append({
                "id": txn.id,
                "date": txn.date.isoformat(),
                "merchant": txn.merchant_name,
                "category": txn.category_name,
                "amount": float(txn.amount),
                "mean_for_category": round(mean, 2),
                "std_dev": round(std_dev, 2),
                "threshold": round(threshold, 2),
            })

    return {
        "anomalies": sorted(anomalies, key=lambda x: x["amount"], reverse=True)
    }


async def detect_recurring(
    db: AsyncSession,
    user_id: int,
    min_occurrences: int = 3,
) -> Dict:
    """
    Detect recurring transactions (same merchant multiple times).

    Args:
        db: Database session
        user_id: User ID
        min_occurrences: Minimum times to count as recurring

    Returns:
        List of recurring merchants
    """

    query = select(Transaction).where(
        Transaction.user_id == user_id
    ).order_by(Transaction.date)

    result = await db.execute(query)
    transactions = result.scalars().all()

    # Group by merchant
    merchants = {}
    for txn in transactions:
        merchant = txn.merchant_name
        if merchant not in merchants:
            merchants[merchant] = []
        merchants[merchant].append(float(txn.amount))

    # Find recurring (appears min_occurrences or more)
    recurring = []
    for merchant, amounts in merchants.items():
        if len(amounts) >= min_occurrences:
            recurring.append({
                "merchant": merchant,
                "count": len(amounts),
                "total": round(sum(amounts), 2),
                "average": round(sum(amounts) / len(amounts), 2),
            })

    return {
        "recurring": sorted(recurring, key=lambda x: x["count"], reverse=True)
    }


async def get_summary(
    db: AsyncSession,
    user_id: int,
) -> Dict:
    """
    Get summary statistics: total spent, avg transaction, top categories.

    Args:
        db: Database session
        user_id: User ID

    Returns:
        Summary statistics
    """

    query = select(Transaction).where(
        Transaction.user_id == user_id
    )

    result = await db.execute(query)
    transactions = result.scalars().all()

    if not transactions:
        return {
            "summary": {
                "total_transactions": 0,
                "total_spent": 0,
                "total_credits": 0,
                "average_transaction": 0,
                "net_amount": 0,
                "top_category": None,
            }
        }

    # Calculate totals
    total_spent = sum(float(t.amount) for t in transactions if not t.is_credit)
    total_credits = sum(float(t.amount) for t in transactions if t.is_credit)
    net_amount = total_spent - total_credits

    # Top category by spending
    categories = {}
    for txn in transactions:
        if not txn.is_credit:  # Only count charges
            cat = txn.category_name
            if cat not in categories:
                categories[cat] = 0
            categories[cat] += float(txn.amount)

    top_category = max(categories.items(), key=lambda x: x[1])[0] if categories else None

    return {
        "summary": {
            "total_transactions": len(transactions),
            "total_spent": round(total_spent, 2),
            "total_credits": round(total_credits, 2),
            "average_transaction": round(total_spent / len([t for t in transactions if not t.is_credit]), 2) if any(not t.is_credit for t in transactions) else 0,
            "net_amount": round(net_amount, 2),
            "top_category": top_category,
        }
    }
