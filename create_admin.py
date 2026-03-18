"""
Запусти один раз чтобы создать аккаунт администратора:
python create_admin.py
"""
import sys
sys.path.append('.')

from app.database import SessionLocal
from app import models
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_admin():
    db = SessionLocal()
    try:
        # Проверяем что админ не существует
        existing = db.query(models.User).filter(models.User.username == "admin").first()
        if existing:
            print("⚠️  Админ уже существует!")
            print(f"   Логин: admin")
            print(f"   Роль:  {existing.role}")
            return

        admin = models.User(
            email         = "admin@ticketflow.ru",
            username      = "admin",
            password_hash = pwd_context.hash("admin2025"),
            role          = "admin",
            city          = "Москва"
        )
        db.add(admin)
        db.commit()
        print("✅ Администратор создан!")
        print("   Логин:  admin")
        print("   Пароль: admin2025")
        print("   Роль:   admin")
        print("\n⚠️  Смени пароль после первого входа!")
    finally:
        db.close()

if __name__ == "__main__":
    create_admin()
