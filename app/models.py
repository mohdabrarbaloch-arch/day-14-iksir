"""ORM models.

Three tables, each doing one job:

* `User` -- an account, with a bcrypt password hash and a role.
* `Compound` -- a saved structure. The SMILES is stored verbatim and the
  descriptors are recomputed on read rather than cached, so a change to the
  engine can never leave a stale number in the database.
* `ScreenRun` -- one screening job: the target, the compounds submitted, and the
  full result payload as JSON. Storing the whole result (not just the score)
  means a run can be re-opened and audited later, which is the point of the
  project.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    compounds: Mapped[list[Compound]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    runs: Mapped[list[ScreenRun]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class Compound(Base):
    __tablename__ = "compounds"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_compound_owner_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    smiles: Mapped[str] = mapped_column(Text, nullable=False)
    therapeutic_class: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    owner: Mapped[User] = relationship(back_populates="compounds")


class ScreenRun(Base):
    __tablename__ = "screen_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target_slug: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    target_name: Mapped[str] = mapped_column(String(200), nullable=False)
    compound_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # The full ranked result list, serialised. Text rather than a JSON column so
    # the same schema works on SQLite and Postgres without a dialect branch.
    results_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    owner: Mapped[User] = relationship(back_populates="runs")
