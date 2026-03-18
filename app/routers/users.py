from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app import models

router = APIRouter(prefix="/users", tags=["users"])

# GET /users/список покупателей для дашборда организатора
@router.get("/")
def get_buyers(db: Session = Depends(get_db)):
    buyers = db.query(models.User).filter(models.User.role == "buyer").all()
    result = []
    for u in buyers:
        orders = db.query(models.Order).filter(models.Order.buyer_id == u.id).all()
        paid_orders = [o for o in orders if o.status == "paid"]
        total_spent = sum(float(o.total_price) for o in paid_orders)
        result.append({
            "id":           u.id,
            "email":        u.email,
            "username":     u.username,
            "first_name":   "",
            "last_name":    "",
            "phone":        "",
            "city":         u.city or "",
            "orders_count": len(paid_orders),
            "total_spent":  total_spent,
            "created_at":   u.created_at.isoformat() if u.created_at else None
        })
    return result