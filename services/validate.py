"""
Transaction validation service.
"""

from models_pydantic import TransactionCreate
from pydantic import ValidationError


async def validate_transactions(transactions: list[dict]) -> tuple[list[TransactionCreate], list[dict]]:
    """
    Validate a list of transactions with Pydantic.
    Separates valid from invalid transactions.

    Args:
        transactions: List of transaction dicts from Claude

    Returns:
        Tuple of (valid_transactions, invalid_transactions)
    """
    valid = []
    invalid = []

    for txn in transactions:
        try:
            validated = TransactionCreate(**txn)
            valid.append(validated)
        except ValidationError as e:
            invalid.append({
                "transaction": txn,
                "error": str(e)
            })

    return valid, invalid


async def check_control_total(
    transactions: list[TransactionCreate],
    expected_total: float = None
) -> dict:
    """
    Verify that transactions sum to expected total (optional check).

    Args:
        transactions: List of validated transactions
        expected_total: Optional expected sum from statement

    Returns:
        Dict with sum, count, and total mismatch (if expected provided)
    """
    total = sum(
        txn.amount if txn.is_credit else -txn.amount
        for txn in transactions
    )

    result = {
        "count": len(transactions),
        "total": round(total, 2),
        "total_charges": len([t for t in transactions if not t.is_credit]),
        "total_credits": len([t for t in transactions if t.is_credit]),
    }

    if expected_total is not None:
        result["expected_total"] = expected_total
        result["matches"] = abs(result["total"] - expected_total) < 0.01

    return result
