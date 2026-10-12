"""
PDF upload endpoint with async task queue.
"""

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import base64
import uuid

from database import get_db_session
from db_models import User
from celery_tasks import process_pdf_task
from redis_client import get_redis
from models_pydantic import StandardResponse


router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("/", response_model=StandardResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    current_user: User = Depends(lambda: None),  # Placeholder, auth via token
    db: AsyncSession = Depends(get_db_session),
    redis = Depends(get_redis),
):
    """
    Upload a credit card statement PDF for async processing.

    Flow:
    1. Validate file is PDF
    2. Read file into memory
    3. Queue Celery task
    4. Return immediately to user
    5. Background worker processes (extract → parse → validate → save)
    6. Redis pub/sub notifies frontend when done

    Args:
        file: PDF file upload
        current_user: Authenticated user (from token)
        db: Database session
        redis: Redis client

    Returns:
        Response with file_id and status
    """

    # Validate file type
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are allowed"
        )

    # Validate file size (max 10MB)
    file_size = len(await file.read())
    if file_size > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large (max 10MB)"
        )

    # Reset file pointer
    await file.seek(0)

    # Read PDF bytes
    pdf_bytes = await file.read()

    # Generate unique file ID
    file_id = f"pdf_{uuid.uuid4()}"

    # Encode to base64 for Celery (JSON serialization)
    pdf_bytes_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    # Queue background task
    task = process_pdf_task.delay(
        file_id=file_id,
        user_id=current_user.id if current_user else 1,  # Placeholder
        pdf_bytes_b64=pdf_bytes_b64,
    )

    # Store task info in Redis (expires in 24 hours)
    await redis.set(
        f"task:{task.id}",
        file_id,
        ex=86400,
    )

    return StandardResponse(
        success=True,
        data={
            "file_id": file_id,
            "task_id": task.id,
            "status": "processing",
            "message": "PDF uploaded. Processing in background. Check status for updates.",
        }
    )


@router.get("/{file_id}/status")
async def get_upload_status(
    file_id: str,
    redis = Depends(get_redis),
):
    """
    Get the status of a PDF upload.

    Returns:
        Current status: processing, done, error, cached
    """
    status_data = await redis.get(f"upload_status:{file_id}")

    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found or expired"
        )

    return StandardResponse(
        success=True,
        data=json.loads(status_data)
    )
