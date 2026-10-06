from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app import holds_service

router = APIRouter(prefix="/holds", tags=["holds"])


class HoldCreate(BaseModel):
    event_id: int
    seat_ids: List[int] = Field(..., min_length=1, max_length=6)


@router.post("")
@router.post("/")
def create_hold(data: HoldCreate, db: Session = Depends(get_db)):
    event = db.query(models.Event).filter(models.Event.id == data.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Мероприятие не найдено")

    seats = (
        db.query(models.Seat)
        .filter(
            models.Seat.id.in_(data.seat_ids),
            models.Seat.venue_id == event.venue_id,
        )
        .all()
    )
    if len(seats) != len(set(data.seat_ids)):
        raise HTTPException(status_code=400, detail="Некоторые места не найдены для этой площадки")

    blocking = (
        db.query(models.OrderSeat)
        .join(models.Order)
        .filter(
            models.OrderSeat.event_id == data.event_id,
            models.OrderSeat.seat_id.in_(data.seat_ids),
            models.Order.status.in_(["pending", "paid"]),
        )
        .all()
    )
    if blocking:
        raise HTTPException(status_code=409, detail="Место уже занято")

    try:
        return holds_service.create_hard_hold(
            db, data.event_id, list(dict.fromkeys(data.seat_ids))
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{token}")
def get_hold(token: str, db: Session = Depends(get_db)):
    data = holds_service.get_hold(db, token)
    if not data:
        raise HTTPException(status_code=404, detail="Hold не найден или истёк")
    return data


@router.delete("/{token}")
def delete_hold(token: str, db: Session = Depends(get_db)):
    ok = holds_service.release_hold(db, token)
    if not ok:
        raise HTTPException(status_code=404, detail="Hold не найден или уже снят")
    return {"message": "Hold снят", "token": token}
