from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from app.database import get_db
from app import models
import random, string

router = APIRouter(prefix="/orders", tags=["orders"])

# ── Схемы ──
class SeatItem(BaseModel):
    row:  int
    seat: int
    type: str

class OrderCreate(BaseModel):
    event_id:     int
    user_email:   str
    user_name:    str
    user_phone:   str
    seats:        List[SeatItem]
    total_price:  float
    order_number: Optional[str] = None
    is_paid:      Optional[bool] = True  
    ticket_type:  Optional[str] = None     
    quantity:     Optional[int] = None 

# ── Генерация номера билета ──
def gen_ticket_number():
    year = datetime.now().year
    num  = ''.join(random.choices(string.digits, k=6))
    return f"TCK-{year}-{num}"

# ── POST /orders/ — создать заказ ──
@router.post("/")
def create_order(data: OrderCreate, db: Session = Depends(get_db)):

    # 1. Найти или создать покупателя по email
    user = db.query(models.User).filter(models.User.email == data.user_email).first()
    if not user:
        # Создаём гостевого покупателя
        username = "guest_" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        user = models.User(
            email         = data.user_email,
            username      = username,
            password_hash = "guest",
            role          = "buyer",
            city          = ""
        )
        db.add(user)
        db.flush()

    # 2. Проверить что мероприятие существует
    event = db.query(models.Event).filter(models.Event.id == data.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Мероприятие не найдено")

    # 3. Найти venue
    venue = db.query(models.Venue).filter(models.Venue.id == event.venue_id).first()

    # 4. Создать заказ
    order = models.Order(
        buyer_id    = user.id,
        event_id    = data.event_id,
        total_price = data.total_price,
        status      = "paid"
    )
    db.add(order)
    db.flush()

    tickets_created = []

    # 5. Для каждого места создать OrderSeat + Ticket
    for seat_item in data.seats:
        # Найти место в БД
        seat = db.query(models.Seat).filter(
            models.Seat.venue_id    == event.venue_id,
            models.Seat.row_number  == seat_item.row,
            models.Seat.seat_number == seat_item.seat
        ).first()

        if not seat:
            # Если места нет в БД — создаём
            seat = models.Seat(
                venue_id    = event.venue_id,
                row_number  = seat_item.row,
                seat_number = seat_item.seat,
                zone        = "VIP" if seat_item.type == "vip" else "Стандарт"
            )
            db.add(seat)
            db.flush()

        # Проверяем что место не занято
        existing = db.query(models.OrderSeat).filter(
            models.OrderSeat.seat_id  == seat.id,
            models.OrderSeat.event_id == data.event_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Место ряд {seat_item.row}, место {seat_item.seat} уже занято"
            )

        # Создаём OrderSeat
        order_seat = models.OrderSeat(
            order_id    = order.id,
            seat_id     = seat.id,
            event_id    = data.event_id,
            is_reserved = True
        )
        db.add(order_seat)

        # Создаём Ticket
        ticket_num = data.order_number or gen_ticket_number()
        if len(data.seats) > 1:
            ticket_num = gen_ticket_number()  # уникальный для каждого места

        ticket = models.Ticket(
            order_id      = order.id,
            seat_id       = seat.id,
            event_id      = data.event_id,
            ticket_number = ticket_num
        )
        db.add(ticket)
        tickets_created.append(ticket_num)

    db.commit()

    return {
        "message":      "Заказ создан",
        "order_id":     order.id,
        "order_number": tickets_created[0] if tickets_created else gen_ticket_number(),
        "tickets":      tickets_created,
        "buyer_name":   data.user_name,
        "buyer_email":  data.user_email
    }


# ── GET /orders/ — список заказов (для дашборда организатора) ──
@router.get("/")
def get_orders(db: Session = Depends(get_db)):
    orders = db.query(models.Order).order_by(models.Order.created_at.desc()).all()
    result = []
    for o in orders:
        user  = db.query(models.User).filter(models.User.id == o.buyer_id).first()
        event = db.query(models.Event).filter(models.Event.id == o.event_id).first()
        seats_count = db.query(models.OrderSeat).filter(models.OrderSeat.order_id == o.id).count()
        result.append({
            "id":            o.id,
            "created_at":    o.created_at.isoformat() if o.created_at else None,
            "user_email":    user.email    if user  else "—",
            "user_name":     user.username if user  else "—",
            "event_id":      o.event_id,
            "event_title":   event.title   if event else "—",
            "tickets_count": seats_count,
            "total_price":   float(o.total_price),
            "is_paid":       o.status == "paid",
            "is_cancelled":  o.status == "cancelled"
        })
    return result


# ── GET /orders/event/{event_id} — занятые места мероприятия ──
@router.get("/event/{event_id}/seats")
def get_event_seats(event_id: int, db: Session = Depends(get_db)):
    order_seats = db.query(models.OrderSeat).filter(
        models.OrderSeat.event_id == event_id
    ).all()
    result = []
    for os in order_seats:
        seat = db.query(models.Seat).filter(models.Seat.id == os.seat_id).first()
        if seat:
            result.append({
                "row_number":  seat.row_number,
                "seat_number": seat.seat_number,
                "seat_type":   seat.zone,
                "status":      "booked"
            })
    return result