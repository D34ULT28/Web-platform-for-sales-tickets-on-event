# TicketFlow — MVP курсовой (Seat Hold)

Учебная веб-платформа продажи билетов с **гарантированным резервированием мест (hard hold)** на PostgreSQL.

## Что реализовано

1. Мероприятия и схема зала (свободные / held / sold)
2. **Hard hold в PostgreSQL** — TTL 10 минут, таблица `seat_holds`
3. Жизненный цикл заказа: `pending` → `paid` / `cancelled` / `expired`
4. Заглушка оплаты `POST /orders/{id}/pay`
5. Простой QR-код на билет (`/static/qr/...`)

## Что сознательно не входит в MVP

- Redis / Kafka / soft hold / ML-антифрод / waiting room / ЮKassa / ОФД

## Стек

- FastAPI + SQLAlchemy + Jinja2
- PostgreSQL (единственная БД — и данные, и hold)

## Быстрый старт

1. Запусти **PostgreSQL** (служба Windows). pgAdmin включать не обязательно.

2. Скопируй env:

```bash
copy .env.example .env
```

Проверь `DATABASE_URL` (логин, пароль, имя БД).

3. Установи зависимости:

```bash
venv\Scripts\activate
pip install -r requirements.txt
```

4. Запуск:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

5. Открой `http://127.0.0.1:8000/event?id=1` (подставь ID мероприятия).

## Сценарий покупки

1. Выбор мест → «Перейти к оплате» создаёт hold в БД (таймер 10 мин)
2. «Оплатить» → заказ `pending` → заглушка `pay` → `paid` + QR
3. По истечении TTL место снова свободно
