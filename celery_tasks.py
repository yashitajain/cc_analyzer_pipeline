"""
Celery background tasks for async PDF processing.
"""

from celery import Celery
from config import settings
from services.extract import extract_text_from_pdf, get_pdf_hash
from services.parse import parse_transactions_with_claude
from services.validate import validate_transactions
from database import AsyncSessionLocal
from db_models import Transaction, ProcessedFile, User
from sqlalchemy import select
import json
import redis.asyncio as aioredis
import asyncio


# Initialize Celery
celery_app = Celery(
    "cc_pipeline",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(bind=True, name="process_pdf")
def process_pdf_task(self, file_id: str, user_id: int, pdf_bytes_b64: str):
    """
    Background task to process PDF upload.

    Steps:
    1. Extract text from PDF
    2. Check if already processed (via hash)
    3. Call Claude API
    4. Validate transactions
    5. Save to database
    6. Notify frontend via Redis Pub/Sub

    Args:
        file_id: Unique file identifier
        user_id: User who uploaded the file
        pdf_bytes_b64: PDF content as base64 string
    """

    # Run async code in sync Celery task
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(
            _process_pdf_async(file_id, user_id, pdf_bytes_b64)
        )
    except Exception as e:
        # Update status in Redis
        loop.run_until_complete(_notify_error(user_id, file_id, str(e)))
        raise


async def _process_pdf_async(file_id: str, user_id: int, pdf_bytes_b64: str):
    """Helper to run async processing."""
    import base64

    redis = aioredis.from_url(settings.REDIS_URL)

    try:
        # Decode PDF
        pdf_bytes = base64.b64decode(pdf_bytes_b64)

        # Step 1: Extract text
        await _notify_status(redis, user_id, file_id, "extracting")
        pdf_text = await extract_text_from_pdf(pdf_bytes)

        # Step 2: Check if already processed
        pdf_hash = await get_pdf_hash(pdf_bytes)
        async with AsyncSessionLocal() as db:
            stmt = select(ProcessedFile).where(ProcessedFile.file_hash == pdf_hash)
            result = await db.execute(stmt)
            existing = result.scalar()

            if existing:
                await _notify_status(redis, user_id, file_id, "cached")
                # Return cached transactions
                # (In real app, fetch from database)
                return

        # Step 3: Call Claude API
        await _notify_status(redis, user_id, file_id, "parsing")
        transactions = await parse_transactions_with_claude(pdf_text)

        # Step 4: Validate
        await _notify_status(redis, user_id, file_id, "validating")
        valid_txns, invalid = await validate_transactions(
            [t.dict() for t in transactions]
        )

        # Step 5: Save to database
        await _notify_status(redis, user_id, file_id, "saving")
        async with AsyncSessionLocal() as db:
            # Get user
            stmt = select(User).where(User.id == user_id)
            result = await db.execute(stmt)
            user = result.scalar()

            if not user:
                raise ValueError("User not found")

            # Save each transaction
            for txn in valid_txns:
                db_txn = Transaction(
                    user_id=user_id,
                    date=txn.date,
                    merchant_name=txn.merchant_name,
                    category_name=txn.category,
                    amount=txn.amount,
                    is_credit=txn.is_credit,
                    source_file=file_id,
                )
                db.add(db_txn)

            # Save processed file record
            processed = ProcessedFile(
                user_id=user_id,
                file_hash=pdf_hash,
                original_filename=file_id,
                transaction_count=len(valid_txns),
                token_usage=0,  # Track if needed
            )
            db.add(processed)

            await db.commit()

        # Step 6: Notify success
        await _notify_status(redis, user_id, file_id, "done")
        await redis.publish(
            f"user:{user_id}:uploads",
            json.dumps({
                "status": "done",
                "file_id": file_id,
                "transactions_count": len(valid_txns),
                "invalid_count": len(invalid),
            })
        )

    except Exception as e:
        await _notify_error(redis, user_id, file_id, str(e))
    finally:
        await redis.close()


async def _notify_status(redis, user_id: int, file_id: str, status: str):
    """Publish status update to Redis."""
    await redis.publish(
        f"user:{user_id}:uploads",
        json.dumps({"file_id": file_id, "status": status})
    )
    print(f"[{file_id}] Status: {status}")


async def _notify_error(redis, user_id: int, file_id: str, error: str):
    """Publish error update to Redis."""
    await redis.publish(
        f"user:{user_id}:uploads",
        json.dumps({"file_id": file_id, "status": "error", "error": error})
    )
    print(f"[{file_id}] Error: {error}")
