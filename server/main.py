# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from server.utils.template_engine import templates
from server.db.db import init_db
from server.auth.routes import router as auth_router
from server.chat.routes import router as chat_router
from server.pages.routes import router as pages_router
from server.chat.routes import router as websocket_router

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI()

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(pages_router)
app.include_router(websocket_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "server" / "static"), name="static")
app.templates = templates



init_db()