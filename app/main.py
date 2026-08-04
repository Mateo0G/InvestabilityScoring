from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.models.db import init_db
from app.routes import upload

app = FastAPI(title="Investor Scoring")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(upload.router)


@app.on_event("startup")
def on_startup():
    init_db()
