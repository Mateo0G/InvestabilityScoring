import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.models.db import init_db
from app.routes import upload

app = FastAPI(title="Investor Scoring")

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(_STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
app.include_router(upload.router)


@app.on_event("startup")
def on_startup():
    init_db()
