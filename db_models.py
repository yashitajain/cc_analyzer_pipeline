"""
SQLAlchemy ORM models for database tables.
These define what User and Transaction rows look like in Postgres.
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid


Base = declarative_base()


class User(Base):
    """User table."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"


class Transaction(Base):
    """Transaction table."""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Transaction details
    date = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    merchant_name = Column(String, nullable=False, index=True)
    category_name = Column(String, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    is_credit = Column(Boolean, default=False)

    # Metadata
    source_file = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    user = relationship("User", back_populates="transactions")

    def __repr__(self):
        return f"<Transaction(id={self.id}, merchant={self.merchant_name}, amount={self.amount})>"


class ProcessedFile(Base):
    """Track which files have been processed (to avoid duplicates)."""
    __tablename__ = "processed_files"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    file_hash = Column(String, unique=True, nullable=False, index=True)
    filename = Column(String, nullable=False)
    transaction_count = Column(Integer, default=0)
    extracted_total = Column(Float, default=0.0)

    # Processing metadata
    latency_ms = Column(Float, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    estimated_cost_usd = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<ProcessedFile(id={self.id}, filename={self.filename})>"
