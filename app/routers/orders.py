from datetime import datetime, timedelta, timezone
from typing import List, Optional
import random
import string

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app import holds_service
from app.qr_util import generate_ticket_qr
from app.holds_service import HOLD_TTL_SECONDS

router = APIRouter(prefix="/orders", tags=["orders"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def gen_ticket_number() -> str:
    year = datetime.now().year
    num = "".join(random.choices(string.digits, k=6))
    return f"TCK-{year}-{num}"


def release_order_seats(db: Session, order: models.Order) -> None:
    db.query(models.OrderSeat).filter(models.OrderSeat.order_id == order.id).delete()


def expire_if_needed(db: Session, order: models.Order) -> models.Order:
    if order.status != "pending":
        return order
    if order.expires_at and order.expires_at < _utcnow():
        order.status = "expired"
        release_order_seats(db, order)
        if order.hold_token:
            holds_service.release_hold(db, order.hold_token)
        else:
            db.commit()
        db.refresh(order)
    return order


class SeatItem(BaseModel):
    row: int
    seat: int
    type: str  # "standard" или "vip"


class OrderCreate(BaseModel):
    event_id: int
    user_email: str
    user_name: str
    user_phone: str
    seats: List[SeatItem]
    total_price: float
    hold_token: str
    order_number: Optional[str] = None


@router.post("/")
def create_order(data: OrderCreate, db: Session = Depends(get_db)):
    event = db.query(models.Event).filter(models.Event.id == data.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Мероприятие не найдено")

    # Resolve seats by row/number
    seat_rows = []
    for seat_item in data.seats:
        seat = (
            db.query(models.Seat)
            .filter(
                models.Seat.venue_id == event.venue_id,
                models.Seat.row_number == seat_item.row,
                models.Seat.seat_number == seat_item.seat,
            )
            .first()
        )
        if not seat:
            seat = models.Seat(
                venue_id=event.venue_id,
                row_number=seat_item.row,
                seat_number=seat_item.seat,
                zone="VIP" if seat_item.type == "vip" else "Стандарт",
            )
            db.add(seat)
            db.flush()
        seat_rows.append(seat)

    seat_ids = [s.id for s in seat_rows]

    try:
        holds_service.assert_hold_matches(db, data.hold_token, data.event_id, seat_ids)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Double-check DB occupancy
    existing = (
        db.query(models.OrderSeat)
        .join(models.Order)
        .filter(
            models.OrderSeat.event_id == data.event_id,
            models.OrderSeat.seat_id.in_(seat_ids),
            models.Order.status.in_(["pending", "paid"]),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Место уже занято")

    user = db.query(models.User).filter(models.User.email == data.user_email).first()
    if not user:
        username = "guest_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        user = models.User(
            email=data.user_email,
            username=username,
            password_hash="guest",
            role="buyer",
            city="",
        )
        db.add(user)
        db.flush()

    expires_at = _utcnow() + timedelta(seconds=HOLD_TTL_SECONDS)
    hold = holds_service.get_hold(db, data.hold_token)
    if hold and hold.get("ttl_seconds") is not None:
        expires_at = _utcnow() + timedelta(seconds=max(int(hold["ttl_seconds"]), 0))

    order = models.Order(
        buyer_id=user.id,
        event_id=data.event_id,
        total_price=data.total_price,
        status="pending",
        hold_token=data.hold_token,
        expires_at=expires_at,
    )
    db.add(order)
    db.flush()

    for seat in seat_rows:
        db.add(
            models.OrderSeat(
                order_id=order.id,
                seat_id=seat.id,
                event_id=data.event_id,
                is_reserved=True,
            )
        )

    db.add(
        models.OrderLog(
            order_id=order.id,
            old_status=None,
            new_status="pending",
        )
    )
    db.commit()
    db.refresh(order)

    return {
        "message": "Заказ создан",
        "order_id": order.id,
        "status": order.status,
        "hold_token": order.hold_token,
        "expires_at": order.expires_at.isoformat() if order.expires_at else None,
        "ttl_seconds": hold.get("ttl_seconds") if hold else HOLD_TTL_SECONDS,
        "buyer_name": data.user_name,
        "buyer_email": data.user_email,
    }


@router.post("/{order_id}/pay")
def pay_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    order = expire_if_needed(db, order)
    if order.status == "expired":
        raise HTTPException(status_code=410, detail="Время бронирования истекло")
    if order.status == "paid":
        tickets = db.query(models.Ticket).filter(models.Ticket.order_id == order.id).all()
        return {
            "message": "Уже оплачен",
            "order_id": order.id,
            "status": "paid",
            "tickets": [
                {"ticket_number": t.ticket_number, "qr_url": t.pdf_path}
                for t in tickets
            ],
        }
    if order.status != "pending":
        raise HTTPException(status_code=400, detail=f"Нельзя оплатить заказ в статусе {order.status}")

    if order.hold_token:
        hold = holds_service.get_hold(db, order.hold_token)
        if not hold:
            order.status = "expired"
            release_order_seats(db, order)
            db.commit()
            raise HTTPException(status_code=410, detail="Время бронирования истекло")

    old_status = order.status
    order.status = "paid"

    order_seats = db.query(models.OrderSeat).filter(models.OrderSeat.order_id == order.id).all()
    tickets_out = []
    for os in order_seats:
        ticket_num = gen_ticket_number()
        qr_url = generate_ticket_qr(ticket_num)
        ticket = models.Ticket(
            order_id=order.id,
            seat_id=os.seat_id,
            event_id=order.event_id,
            ticket_number=ticket_num,
            pdf_path=qr_url,
        )
        db.add(ticket)
        tickets_out.append({"ticket_number": ticket_num, "qr_url": qr_url, "seat_id": os.seat_id})

    db.add(models.OrderLog(order_id=order.id, old_status=old_status, new_status="paid"))
    db.commit()

    if order.hold_token:
        holds_service.release_hold(db, order.hold_token)

    return {
        "message": "Оплата подтверждена",
        "order_id": order.id,
        "status": "paid",
        "tickets": tickets_out,
        "order_number": tickets_out[0]["ticket_number"] if tickets_out else None,
    }


@router.post("/{order_id}/cancel")
def cancel_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    if order.status in ("cancelled", "expired"):
        return {"message": "Уже отменён", "order_id": order.id, "status": order.status}
    if order.status == "paid":
        raise HTTPException(status_code=400, detail="Оплаченный заказ отменяйте через возврат")

    old = order.status
    order.status = "cancelled"
    release_order_seats(db, order)
    if order.hold_token:
        holds_service.release_hold(db, order.hold_token)
    db.add(models.OrderLog(order_id=order.id, old_status=old, new_status="cancelled"))
    db.commit()
    return {"message": "Заказ отменён", "order_id": order.id, "status": "cancelled"}


@router.get("/")
def get_orders(db: Session = Depends(get_db)):
    orders = db.query(models.Order).order_by(models.Order.created_at.desc()).all()
    result = []
    for o in orders:
        o = expire_if_needed(db, o)
        user = db.query(models.User).filter(models.User.id == o.buyer_id).first()
        event = db.query(models.Event).filter(models.Event.id == o.event_id).first()
        seats_count = db.query(models.OrderSeat).filter(models.OrderSeat.order_id == o.id).count()
        result.append(
            {
                "id": o.id,
                "created_at": o.created_at.isoformat() if o.created_at else None,
                "user_email": user.email if user else "—",
                "user_name": user.username if user else "—",
                "event_id": o.event_id,
                "event_title": event.title if event else "—",
                "tickets_count": seats_count,
                "total_price": float(o.total_price),
                "status": o.status,
                "is_paid": o.status == "paid",
                "is_cancelled": o.status == "cancelled",
            }
        )
    return result


@router.get("/event/{event_id}/seats")
def get_event_seats(event_id: int, db: Session = Depends(get_db)):
    """Occupied seats for legacy frontend (booked = pending/paid)."""
    order_seats = (
        db.query(models.OrderSeat)
        .join(models.Order)
        .filter(
            models.OrderSeat.event_id == event_id,
            models.Order.status.in_(["pending", "paid"]),
        )
        .all()
    )
    result = []
    for os in order_seats:
        order = db.query(models.Order).filter(models.Order.id == os.order_id).first()
        if order:
            expire_if_needed(db, order)
            if order.status not in ("pending", "paid"):
                continue
        seat = db.query(models.Seat).filter(models.Seat.id == os.seat_id).first()
        if seat:
            result.append(
                {
                    "row_number": seat.row_number,
                    "seat_number": seat.seat_number,
                    "seat_type": seat.zone,
                    "status": "booked" if order and order.status == "pending" else "sold",
                }
            )
    return result


@router.get("/find-by-ticket")
def find_by_ticket(ticket_number: str, email: str, db: Session = Depends(get_db)):
    ticket = db.query(models.Ticket).filter(models.Ticket.ticket_number == ticket_number).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Билет не найден")

    order = db.query(models.Order).filter(models.Order.id == ticket.order_id).first()
    user = db.query(models.User).filter(models.User.id == order.buyer_id).first()

    if not user or user.email.lower() != email.lower():
        raise HTTPException(status_code=403, detail="Email не совпадает с данными заказа")
    if order.status == "cancelled":
        raise HTTPException(status_code=400, detail="Этот заказ уже отменён")

    event = db.query(models.Event).filter(models.Event.id == order.event_id).first()
    seat = db.query(models.Seat).filter(models.Seat.id == ticket.seat_id).first()
    venue = db.query(models.Venue).filter(models.Venue.id == event.venue_id).first() if event else None

    return {
        "order_id": order.id,
        "ticket_number": ticket.ticket_number,
        "qr_url": ticket.pdf_path,
        "event_title": event.title if event else "—",
        "event_date": event.event_date.isoformat() if event else None,
        "venue": (venue.city + ", " + venue.name) if venue else "—",
        "seat": f"Ряд {seat.row_number}, место {seat.seat_number}" if seat else "—",
        "seat_type": seat.zone if seat else "Стандарт",
        "total_price": float(order.total_price),
        "buyer_email": user.email,
        "status": order.status,
    }


class CancelByTicketRequest(BaseModel):
    ticket_number: str
    email: str


@router.post("/cancel-by-ticket")
def cancel_by_ticket(data: CancelByTicketRequest, db: Session = Depends(get_db)):
    ticket = db.query(models.Ticket).filter(models.Ticket.ticket_number == data.ticket_number).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Билет не найден")

    order = db.query(models.Order).filter(models.Order.id == ticket.order_id).first()
    user = db.query(models.User).filter(models.User.id == order.buyer_id).first()

    if not user or user.email.lower() != data.email.lower():
        raise HTTPException(status_code=403, detail="Email не совпадает с данными заказа")
    if order.status == "cancelled":
        raise HTTPException(status_code=400, detail="Заказ уже отменён")

    old = order.status
    order.status = "cancelled"
    release_order_seats(db, order)
    db.add(models.OrderLog(order_id=order.id, old_status=old, new_status="cancelled"))
    db.commit()
    return {"message": "Возврат оформлен", "order_id": order.id, "ticket_number": data.ticket_number}
