# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.params import Form
from fastapi.requests import Request
import json
from pathlib import Path
from server.utils.template_engine import templates
from server.db.db import init_db
from server.auth.routes import router as auth_router
from server.chat.routes import router as chat_router
from server.pages.routes import router as pages_router

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI()

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(pages_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://chat.socksthoughtshop.lol:8118",
        "http://chat.socksthoughtshop.lol:8118",
        "https://socksthoughtshop.lol",
        "http://socksthoughtshop.lol",
        "http://localhost:8000",  # For local development
        "http://127.0.0.1:8000"   # For local development
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Accept",
        "Accept-Language",
        "Content-Language",
        "Content-Type",
        "Authorization",
        "Cookie",
        "Set-Cookie",
        "Access-Control-Allow-Credentials",
        "Access-Control-Allow-Origin"
    ],
)

app.mount("/static", StaticFiles(directory=BASE_DIR /
          "server" / "static"), name="static")
app.templates = templates


DATA_PATH = Path("data.json")


@app.get("/form", response_class=HTMLResponse)
async def get_form(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})


init_db()
