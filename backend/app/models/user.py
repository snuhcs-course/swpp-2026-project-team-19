# AI-generated with ChatGPT (Haeul Yang, 2026-10-04, PR #3). Reviewed by Haeul Yang.
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum as SQLAlchemyEnum, String, func, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class UserType(str, Enum):
    CUSTOMER = "customer"
    OPERATOR = "operator"


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    auth_subject: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_type: Mapped[UserType] = mapped_column(
        SQLAlchemyEnum(
            UserType,
            name="user_type",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=UserType.CUSTOMER,
        server_default=text("'customer'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
