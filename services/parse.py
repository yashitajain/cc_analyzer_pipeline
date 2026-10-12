"""
Claude API service for transaction extraction and parsing.
"""

from anthropic import Anthropic
from config import settings
from models_pydantic import TransactionCreate
from pydantic import ValidationError
import json


client = Anthropic()


async def parse_transactions_with_claude(pdf_text: str) -> list[TransactionCreate]:
    """
    Parse transactions from PDF text using Claude API.

    Args:
        pdf_text: Extracted text from PDF

    Returns:
        List of validated TransactionCreate objects

    Raises:
        ValueError: If Claude response invalid or parsing fails
    """

    # Prompt Claude to extract transactions
    prompt = f"""
Analyze this credit card statement text and extract all transactions.

For each transaction, provide:
- date (YYYY-MM-DD format)
- merchant_name (clean merchant name, no extra symbols)
- amount (positive number, rounded to 2 decimals)
- category (one of: Travel, Dining, Shopping, Grocery, Subscription, Transportation, Entertainment, Transfer, Misc)
- is_credit (true if credit/refund, false if charge)

Return ONLY a JSON array. No markdown, no explanation. Example:
[
  {{"date": "2024-09-15", "merchant_name": "Starbucks", "amount": 5.50, "category": "Dining", "is_credit": false}},
  {{"date": "2024-09-16", "merchant_name": "Refund", "amount": 25.00, "category": "Misc", "is_credit": true}}
]

Credit card statement text:
{pdf_text}
"""

    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4096,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        response_text = message.content[0].text.strip()

        # Parse JSON response
        transactions_data = json.loads(response_text)

        # Validate each transaction with Pydantic
        transactions = []
        for txn in transactions_data:
            try:
                validated = TransactionCreate(**txn)
                transactions.append(validated)
            except ValidationError as e:
                print(f"Skipping invalid transaction: {txn} - {e}")
                continue

        if not transactions:
            raise ValueError("No valid transactions extracted")

        return transactions

    except json.JSONDecodeError as e:
        raise ValueError(f"Claude response was not valid JSON: {str(e)}")
    except Exception as e:
        raise ValueError(f"Failed to parse transactions: {str(e)}")
