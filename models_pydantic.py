"""
Pydantic models for request/response validation.
These ensure data conforms to expected structure before saving.
"""

from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Optional, List


# ============================================================================
# User Models
# ============================================================================

class UserCreate(BaseModel):
    """User registration request."""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    email: Optional[str] = None


class UserLogin(BaseModel):
    """User login request."""
    username: str
    password: str


class UserResponse(BaseModel):
    """User response (never expose password)."""
    id: int
    username: str
    email: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True  # Allows ORM model conversion


class AuthToken(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    user_id: int


# ============================================================================
# Transaction Models
# ============================================================================

class TransactionCreate(BaseModel):
    """Create transaction (from extraction)."""
    date: str  # YYYY-MM-DD
    merchant: str
    category: str  # One of: Travel, Dining, Shopping, Grocery, Subscription, Transportation, Entertainment, Transfer, Misc
    amount: float
    is_credit: bool = False
    source_file: str
    card_name: str  

    @validator("amount")
    def amount_positive(cls, v):
        if v <= 0:
            raise ValueError("Amount must be positive")
        return round(v, 2)

    @validator("category")
    def category_valid(cls, v):
        valid = {
            "Travel", "Dining", "Shopping", "Grocery", "Subscription",
            "Transportation", "Entertainment", "Transfer", "Misc"
        }
        if v not in valid:
            raise ValueError(f"Invalid category: {v}. Must be one of {valid}")
        return v


class TransactionResponse(BaseModel):
    """Transaction response."""
    id: int
    user_id: int
    date: str
    merchant: str
    category: str
    amount: float
    is_credit: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionListResponse(BaseModel):
    """Multiple transactions."""
    transactions: List[TransactionResponse]
    total_count: int
    page: int
    page_size: int


# ============================================================================
# Extraction Models
# ============================================================================

class ExtractionResult(BaseModel):
    """Result of PDF extraction."""
    job_id: str
    status: str  # "processing" | "success" | "error"
    transaction_count: int = 0
    extracted_total: float = 0.0
    error: Optional[str] = None
    transactions: List[TransactionCreate] = []


class ValidationError(BaseModel):
    """Validation error response."""
    field: str
    error: str


class StandardResponse(BaseModel):
    """Standard API response wrapper."""
    status: str  # "ok" | "error"
    data: Optional[dict] = None
    error: Optional[str] = None
    errors: List[ValidationError] = []
