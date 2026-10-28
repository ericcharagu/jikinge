from datetime import datetime
from typing import Any

from sqlalchemy import DECIMAL, TIMESTAMP, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, mapped_column

from config import settings

# Base class for all models
Base = declarative_base()


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_name: Mapped[str] = mapped_column(index=True)
    insurance_type: Mapped[str] = mapped_column(index=True)
    premium: Mapped[DECIMAL] = mapped_column(DECIMAL)


class DeductiblesOrm(Base):
    __tablename__ = "deductibles"

    id: Mapped[int] = mapped_column(primary_key=True)
    deductible_type: Mapped[str] = mapped_column(String, index=True)
    deductible_name: Mapped[str] = mapped_column(String)
    deductible_value: Mapped[str] = mapped_column(String)


class PremiumsOrm(Base):
    __tablename__ = "Premiums"
    id: Mapped[int] = mapped_column(primary_key=True)
    premium_name: Mapped[str] = mapped_column(String)
    premium_value: Mapped[str] = mapped_column(String)


class InteractionLogOrm(Base):
    """Maps the interaction log to the DB data"""

    __tablename__ = "interaction_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[bytes] = mapped_column(index=True)
    cart_id: Mapped[str] = mapped_column(String, index=True)
    user_message: Mapped[str] = mapped_column(String)
    llm_response: Mapped[str] = mapped_column(String)
    llm_message_type: Mapped[str] = mapped_column(String, index=True)
    intent: Mapped[str] = mapped_column(String, index=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    cart_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(settings.NAIROBI_TZ),
    )
