"""Hard seat hold helpers — PostgreSQL only (no Redis)."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models

HOLD_TTL_SECONDS = int(os.getenv("HOLD_TTL_SECONDS", "600"))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _purge_expired(db: Session, event_id: Optional[int] = None) -> None:
    q = db.query(models.SeatHold).filter(models.SeatHold.expires_at < _utcnow())
    if event_id is not None:
        q = q.filter(models.SeatHold.event_id == event_id)
    q.delete(synchronize_session=False)


def create_hard_hold(db: Session, event_id: int, seat_ids: List[int]) -> dict:
    if not seat_ids:
        raise ValueError("Нужно выбрать хотя бы одно место")
    if len(seat_ids) != len(set(seat_ids)):
        raise ValueError("Дубликаты мест в запросе")

    _purge_expired(db, event_id)

    existing = (
        db.query(models.SeatHold)
        .filter(
            models.SeatHold.event_id == event_id,
            models.SeatHold.seat_id.in_(seat_ids),
            models.SeatHold.expires_at >= _utcnow(),
        )
        .first()
    )
    if existing:
        raise RuntimeError(f"Место {existing.seat_id} только что занято")

    token = str(uuid.uuid4())
    expires_at = _utcnow() + timedelta(seconds=HOLD_TTL_SECONDS)

    try:
        for seat_id in seat_ids:
            db.add(
                models.SeatHold(
                    token=token,
                    event_id=event_id,
                    seat_id=seat_id,
                    expires_at=expires_at,
                )
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise RuntimeError("Место только что занято")

    return {
        "token": token,
        "event_id": event_id,
        "seat_ids": seat_ids,
        "ttl_seconds": HOLD_TTL_SECONDS,
        "expires_at": expires_at.isoformat(),
    }


def get_hold(db: Session, token: str) -> Optional[dict]:
    _purge_expired(db)
    rows = (
        db.query(models.SeatHold)
        .filter(models.SeatHold.token == token, models.SeatHold.expires_at >= _utcnow())
        .all()
    )
    if not rows:
        return None

    expires_at = min(r.expires_at for r in rows)
    ttl = max(int((expires_at - _utcnow()).total_seconds()), 0)
    return {
        "token": token,
        "event_id": rows[0].event_id,
        "seat_ids": [r.seat_id for r in rows],
        "ttl_seconds": ttl,
        "expires_at": expires_at.isoformat(),
        "created_at": rows[0].created_at.isoformat() if rows[0].created_at else None,
    }


def release_hold(db: Session, token: str) -> bool:
    deleted = (
        db.query(models.SeatHold)
        .filter(models.SeatHold.token == token)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted > 0


def held_seat_ids_for_event(db: Session, event_id: int, seat_ids: List[int]) -> set:
    if not seat_ids:
        return set()
    _purge_expired(db, event_id)
    rows = (
        db.query(models.SeatHold.seat_id)
        .filter(
            models.SeatHold.event_id == event_id,
            models.SeatHold.seat_id.in_(seat_ids),
            models.SeatHold.expires_at >= _utcnow(),
        )
        .all()
    )
    return {r[0] for r in rows}


def assert_hold_matches(db: Session, token: str, event_id: int, seat_ids: List[int]) -> dict:
    data = get_hold(db, token)
    if not data:
        raise ValueError("Hold истёк или не найден")
    if int(data["event_id"]) != int(event_id):
        raise ValueError("Hold относится к другому мероприятию")
    held = sorted(int(x) for x in data["seat_ids"])
    wanted = sorted(int(x) for x in seat_ids)
    if held != wanted:
        raise ValueError("Места заказа не совпадают с hold")
    return data
