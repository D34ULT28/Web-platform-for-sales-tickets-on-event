from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.database import engine
from app import models
from app.routers import auth, events, venues, seats, orders, users, holds

models.Base.metadata.create_all(bind=engine)


def ensure_schema():
    """Add MVP columns if the DB was created before this release (PostgreSQL)."""
    statements = [
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS hold_token VARCHAR(36)",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP",
    ]
    try:
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
    except Exception:
        # Non-Postgres or missing permissions — create_all covers fresh DBs
        pass


ensure_schema()

app = FastAPI(title="Ticket Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(auth.router)
app.include_router(events.router)
app.include_router(venues.router)
app.include_router(seats.router)
app.include_router(orders.router)
app.include_router(users.router)
app.include_router(holds.router)


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/event")
def event_page(request: Request):
    return templates.TemplateResponse("event.html", {"request": request})
