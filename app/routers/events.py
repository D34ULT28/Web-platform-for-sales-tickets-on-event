from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.database import get_db
from app import models

router = APIRouter(prefix="/events", tags=["events"])

class EventCreate(BaseModel):
    title:          str
    description:    Optional[str] = ""
    category:       Optional[str] = "Концерт"
    event_date:     datetime
    venue_id:       int
    organizer_id:   int
    price_standard: float = 0
    price_vip:      float = 0

class EventUpdate(BaseModel):
    title:          Optional[str] = None
    description:    Optional[str] = None
    category:       Optional[str] = None
    event_date:     Optional[datetime] = None
    price_standard: Optional[float] = None
    price_vip:      Optional[float] = None
    status:         Optional[str] = None

def event_to_dict(event, db):
    """Конвертирует Event в словарь с city и venue_name для фронтенда"""
    venue = db.query(models.Venue).filter(models.Venue.id == event.venue_id).first()
    return {
        "id":             event.id,
        "title":          event.title,
        "description":    event.description or "",
        "category":       event.category or "Концерт",
        "event_date":     event.event_date.isoformat() if event.event_date else None,
        "venue_id":       event.venue_id,
        "venue_name":     venue.name    if venue else "—",
        "city":           venue.city    if venue else "—",
        "organizer_id":   event.organizer_id,
        "price_standard": float(event.price_standard or 0),
        "price_vip":      float(event.price_vip or 0),
        "status":         event.status,
        "total_seats":    (venue.total_rows * venue.seats_per_row) if venue else 50
    }

# GET /events/ — все активные мероприятия
@router.get("/")
def get_events(category: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.Event).filter(models.Event.status == "active")
    if category:
        query = query.filter(models.Event.category == category)
    events = query.order_by(models.Event.event_date).all()
    return [event_to_dict(e, db) for e in events]

# GET /events/{id} — одно мероприятие
@router.get("/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db)):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Мероприятие не найдено")
    return event_to_dict(event, db)

# POST /events/ — создать мероприятие
@router.post("/")
def create_event(data: EventCreate, db: Session = Depends(get_db)):
    venue = db.query(models.Venue).filter(models.Venue.id == data.venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Зал не найден")

    event = models.Event(
        title          = data.title,
        description    = data.description,
        category       = data.category,
        event_date     = data.event_date,
        venue_id       = data.venue_id,
        organizer_id   = data.organizer_id,
        price_standard = data.price_standard,
        price_vip      = data.price_vip,
        status         = "active"
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return {"message": "Мероприятие создано", "event_id": event.id}

# PATCH /events/{id}
@router.patch("/{event_id}")
def update_event(event_id: int, data: EventUpdate, db: Session = Depends(get_db)):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Мероприятие не найдено")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(event, field, value)
    db.commit()
    db.refresh(event)
    return {"message": "Обновлено", "event_id": event.id}

# DELETE /events/{id}
@router.delete("/{event_id}")
def cancel_event(event_id: int, db: Session = Depends(get_db)):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Мероприятие не найдено")
    event.status = "cancelled"
    db.commit()
    return {"message": "Мероприятие отменено"}