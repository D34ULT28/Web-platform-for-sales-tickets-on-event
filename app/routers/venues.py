from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app import models

router = APIRouter(prefix="/venues", tags=["venues"])

class VenueCreate(BaseModel):
    name:          str
    city:          str = ""
    address:       str = ""
    total_rows:    int
    seats_per_row: int
    created_by:    int

@router.post("/")
def create_venue(data: VenueCreate, db: Session = Depends(get_db)):
    venue = models.Venue(
        name          = data.name,
        city          = data.city,
        address       = data.address,
        total_rows    = data.total_rows,
        seats_per_row = data.seats_per_row,
        created_by    = data.created_by
    )
    db.add(venue)
    db.commit()
    db.refresh(venue)

    # Автоматически генерируем все места для зала
    for row in range(1, data.total_rows + 1):
        for seat in range(1, data.seats_per_row + 1):
            zone = "VIP" if row <= 2 else "Стандарт"
            db.add(models.Seat(
                venue_id    = venue.id,
                row_number  = row,
                seat_number = seat,
                zone        = zone
            ))
    db.commit()

    return {
        "message":  "Зал создан",
        "venue_id": venue.id,
        "seats":    data.total_rows * data.seats_per_row
    }

@router.get("/")
def get_venues(db: Session = Depends(get_db)):
    return db.query(models.Venue).all()

@router.get("/{venue_id}")
def get_venue(venue_id: int, db: Session = Depends(get_db)):
    venue = db.query(models.Venue).filter(models.Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Зал не найден")
    return venue