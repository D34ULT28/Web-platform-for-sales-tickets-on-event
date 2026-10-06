from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app import holds_service

router = APIRouter(tags=["seats"])


@router.get("/events/{event_id}/seats")
def get_seats(event_id: int, db: Session = Depends(get_db)):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Мероприятие не найдено")

    seats = (
        db.query(models.Seat)
        .filter(models.Seat.venue_id == event.venue_id)
        .order_by(models.Seat.row_number, models.Seat.seat_number)
        .all()
    )

    occupied = (
        db.query(models.OrderSeat)
        .join(models.Order)
        .filter(
            models.OrderSeat.event_id == event_id,
            models.Order.status.in_(["pending", "paid"]),
        )
        .all()
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    sold_ids = set()
    reserved_ids = set()

    for os in occupied:
        order = db.query(models.Order).filter(models.Order.id == os.order_id).first()
        if not order:
            continue
        if order.status == "paid":
            sold_ids.add(os.seat_id)
        elif order.status == "pending":
            if order.expires_at and order.expires_at < now:
                order.status = "expired"
                db.query(models.OrderSeat).filter(models.OrderSeat.order_id == order.id).delete()
                if order.hold_token:
                    holds_service.release_hold(db, order.hold_token)
                else:
                    db.commit()
            else:
                reserved_ids.add(os.seat_id)

    held_ids = holds_service.held_seat_ids_for_event(db, event_id, [s.id for s in seats])

    result = []
    for seat in seats:
        if seat.id in sold_ids:
            status = "sold"
        elif seat.id in reserved_ids or seat.id in held_ids:
            status = "held"
        else:
            status = "free"

        result.append(
            {
                "id": seat.id,
                "row_number": seat.row_number,
                "seat_number": seat.seat_number,
                "zone": seat.zone,
                "status": status,
                "price": float(event.price_vip)
                if seat.zone == "VIP"
                else float(event.price_standard),
            }
        )

    return result
