from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import models

router = APIRouter(tags=["seats"])

# Получить все места для мероприятия (для схемы зала)
@router.get("/events/{event_id}/seats")
def get_seats(event_id: int, db: Session = Depends(get_db)):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Мероприятие не найдено")

    seats = db.query(models.Seat).filter(
        models.Seat.venue_id == event.venue_id
    ).order_by(models.Seat.row_number, models.Seat.seat_number).all()

    occupied = db.query(models.OrderSeat).join(models.Order).filter(
        models.OrderSeat.event_id == event_id,
        models.Order.status.in_(["pending", "paid"])
    ).all()
    occupied_ids = {os.seat_id for os in occupied}
    paid_ids = {
        os.seat_id for os in occupied
        if db.query(models.Order).filter(
            models.Order.id == os.order_id,
            models.Order.status == "paid"
        ).first()
    }

    result = []
    for seat in seats:
        if seat.id in paid_ids:
            status = "sold"
        elif seat.id in occupied_ids:
            status = "reserved"
        else:
            status = "free"

        result.append({
            "id":          seat.id,
            "row_number":  seat.row_number,
            "seat_number": seat.seat_number,
            "zone":        seat.zone,
            "status":      status,
            "price":       float(event.price_vip) if seat.zone == "VIP"
                           else float(event.price_standard)
        })

    return result