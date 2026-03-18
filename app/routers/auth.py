from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
from typing import Optional
from app.database import get_db
from app import models

router = APIRouter(prefix="/auth", tags=["auth"])

SECRET_KEY = "ticket_platform_secret_key_2025"
ALGORITHM  = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class RegisterRequest(BaseModel):
    email:    str
    username: str
    password: str
    role:     str = "buyer"
    city:     str = ""

class LoginRequest(BaseModel):
    username: str
    password: str

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_token(user_id: int, role: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=24)
    return jwt.encode(
        {"sub": str(user_id), "role": role, "exp": expire},
        SECRET_KEY, algorithm=ALGORITHM
    )

def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Не авторизован")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Недействительный токен")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return user

def require_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Доступ только для администраторов")
    return current_user

def require_organizer(current_user: models.User = Depends(get_current_user)):
    if current_user.role not in ("organizer", "admin"):
        raise HTTPException(status_code=403, detail="Доступ только для организаторов")
    return current_user

@router.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email уже занят")
    if db.query(models.User).filter(models.User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Логин уже занят")
    if data.role == "admin":
        raise HTTPException(status_code=403, detail="Нельзя зарегистрироваться как администратор")
    user = models.User(
        email         = data.email,
        username      = data.username,
        password_hash = hash_password(data.password),
        role          = data.role,
        city          = data.city
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Регистрация успешна", "user_id": user.id}

@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == data.username).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    token = create_token(user.id, user.role)
    return {
        "access_token": token,
        "token_type":   "bearer",
        "role":         user.role,
        "username":     user.username,
        "user_id":      user.id
    }

@router.get("/me")
def get_me(current_user: models.User = Depends(get_current_user)):
    return {
        "id":       current_user.id,
        "username": current_user.username,
        "email":    current_user.email,
        "role":     current_user.role,
        "city":     current_user.city
    }

@router.get("/admin/users")
def get_all_users(db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    users = db.query(models.User).all()
    return [{
        "id":         u.id,
        "username":   u.username,
        "email":      u.email,
        "role":       u.role,
        "city":       u.city or "—",
        "created_at": u.created_at.isoformat() if u.created_at else None
    } for u in users]

@router.patch("/admin/users/{user_id}/role")
def change_user_role(user_id: int, role: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    if role not in ("buyer", "organizer", "admin"):
        raise HTTPException(status_code=400, detail="Недопустимая роль")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user.role = role
    db.commit()
    return {"message": f"Роль {user.username} изменена на {role}"}

@router.delete("/admin/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if user.role == "admin":
        raise HTTPException(status_code=400, detail="Нельзя удалить администратора")
    db.delete(user)
    db.commit()
    return {"message": f"Пользователь {user.username} удалён"}