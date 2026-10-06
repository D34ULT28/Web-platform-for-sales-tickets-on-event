"""Generate a simple QR PNG for a ticket number."""
from pathlib import Path

import qrcode


QR_DIR = Path(__file__).resolve().parent / "static" / "qr"


def generate_ticket_qr(ticket_number: str) -> str:
    QR_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{ticket_number}.png"
    path = QR_DIR / filename
    img = qrcode.make(ticket_number)
    img.save(path)
    # URL path served by StaticFiles
    return f"/static/qr/{filename}"
