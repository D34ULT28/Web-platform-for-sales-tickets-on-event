from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine
from app import models
from app.routers import auth, events, venues, seats, orders, users

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Ticket Platform")

# ── CORS — разрешаем запросы с фронтенда ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # в продакшене заменить на конкретный домен
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

@app.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})