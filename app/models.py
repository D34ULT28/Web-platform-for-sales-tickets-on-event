from sqlalchemy import Column, Integer, String, Numeric, Boolean, Text, ForeignKey, TIMESTAMP, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True)
    email         = Column(String(255), unique=True, nullable=False)
    username      = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role          = Column(String(20), default="buyer")
    city          = Column(String(100))
    created_at    = Column(TIMESTAMP, server_default=func.now())

class Venue(Base):
    __tablename__ = "venues"
    id            = Column(Integer, primary_key=True)
    name          = Column(String(255), nullable=False)
    city          = Column(String(100))
    address       = Column(String(255))
    total_rows    = Column(Integer, nullable=False)
    seats_per_row = Column(Integer, nullable=False)
    created_by    = Column(Integer, ForeignKey("users.id"))

class Seat(Base):
    __tablename__ = "seats"
    id          = Column(Integer, primary_key=True)
    venue_id    = Column(Integer, ForeignKey("venues.id"), nullable=False)
    row_number  = Column(Integer, nullable=False)
    seat_number = Column(Integer, nullable=False)
    zone        = Column(String(50), default="Стандарт")
    __table_args__ = (UniqueConstraint("venue_id", "row_number", "seat_number"),)

class Event(Base):
    __tablename__ = "events"
    id             = Column(Integer, primary_key=True)
    title          = Column(String(255), nullable=False)
    description    = Column(Text)
    category       = Column(String(50))
    event_date     = Column(TIMESTAMP, nullable=False)
    venue_id       = Column(Integer, ForeignKey("venues.id"), nullable=False)
    organizer_id   = Column(Integer, ForeignKey("users.id"), nullable=False)
    price_standard = Column(Numeric(10,2), default=0)
    price_vip      = Column(Numeric(10,2), default=0)
    status         = Column(String(20), default="active")
    created_at     = Column(TIMESTAMP, server_default=func.now())

class Order(Base):
    __tablename__ = "orders"
    id          = Column(Integer, primary_key=True)
    buyer_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_id    = Column(Integer, ForeignKey("events.id"), nullable=False)
    total_price = Column(Numeric(10,2), nullable=False)
    status      = Column(String(20), default="pending")
    hold_token  = Column(String(36), nullable=True)
    expires_at  = Column(TIMESTAMP, nullable=True)
    created_at  = Column(TIMESTAMP, server_default=func.now())

class OrderSeat(Base):
    __tablename__ = "order_seats"
    id          = Column(Integer, primary_key=True)
    order_id    = Column(Integer, ForeignKey("orders.id"), nullable=False)
    seat_id     = Column(Integer, ForeignKey("seats.id"), nullable=False)
    event_id    = Column(Integer, ForeignKey("events.id"), nullable=False)
    is_reserved = Column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("seat_id", "event_id"),)

class SeatHold(Base):
    """Hard hold места в PostgreSQL (вместо Redis)."""
    __tablename__ = "seat_holds"
    id         = Column(Integer, primary_key=True)
    token      = Column(String(36), nullable=False, index=True)
    event_id   = Column(Integer, ForeignKey("events.id"), nullable=False)
    seat_id    = Column(Integer, ForeignKey("seats.id"), nullable=False)
    expires_at = Column(TIMESTAMP, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    __table_args__ = (UniqueConstraint("event_id", "seat_id"),)

class Ticket(Base):
    __tablename__ = "tickets"
    id            = Column(Integer, primary_key=True)
    order_id      = Column(Integer, ForeignKey("orders.id"), nullable=False)
    seat_id       = Column(Integer, ForeignKey("seats.id"), nullable=False)
    event_id      = Column(Integer, ForeignKey("events.id"), nullable=False)
    ticket_number = Column(String(50), unique=True, nullable=False)
    pdf_path      = Column(String(255))
    created_at    = Column(TIMESTAMP, server_default=func.now())

class OrderLog(Base):
    __tablename__ = "order_logs"
    id         = Column(Integer, primary_key=True)
    order_id   = Column(Integer, ForeignKey("orders.id"), nullable=False)
    old_status = Column(String(20))
    new_status = Column(String(20))
    changed_at = Column(TIMESTAMP, server_default=func.now())

class Notification(Base):
    __tablename__ = "notifications"
    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    message    = Column(Text, nullable=False)
    is_read    = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    