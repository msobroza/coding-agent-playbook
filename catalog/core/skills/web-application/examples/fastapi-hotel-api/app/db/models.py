"""The hotel's tables as SQLAlchemy 2.0 mapped classes; no engine or session is built here."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Final

from sqlalchemy import ForeignKey, Index, MetaData, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

#: Stable constraint names, so migrations can refer to them on every database.
NAMING_CONVENTION: Final = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class RoomRow(Base):
    __tablename__ = "rooms"

    room_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(10))
    capacity: Mapped[int]
    nightly_rate_cents: Mapped[int]
    notes: Mapped[str | None] = mapped_column(String(500))


class CustomerRow(Base):
    __tablename__ = "customers"

    customer_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True)


class BookingRow(Base):
    __tablename__ = "bookings"

    booking_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.room_id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.customer_id"))
    check_in: Mapped[date]
    check_out: Mapped[date]
    price_cents: Mapped[int]
    cancelled_on: Mapped[date | None]
    # lazy="raise": reading nights without an explicit load fails loudly, never queries.
    nights: Mapped[list[RoomNightRow]] = relationship(lazy="raise", cascade="all, delete-orphan")


class RoomNightRow(Base):
    """One booked night of one room; the index lets only one active booking hold it."""

    __tablename__ = "room_nights"
    __table_args__ = (
        Index(
            "one_active_booking_per_room_night",
            "room_id",
            "night",
            unique=True,
            sqlite_where=text("cancelled_on IS NULL"),
            postgresql_where=text("cancelled_on IS NULL"),
        ),
    )

    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.booking_id"), primary_key=True
    )
    night: Mapped[date] = mapped_column(primary_key=True)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.room_id"))
    cancelled_on: Mapped[date | None]
