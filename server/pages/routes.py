from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import jwt, JWTError
from pathlib import Path
from server.utils.template_engine import templates

from server.auth.auth import SECRET_KEY, ALGORITHM

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def get_root_page(request: Request):
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse("/login")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise JWTError()
    except JWTError:
        return RedirectResponse("/login")

    return templates.TemplateResponse("index.html", {"request": request})

@router.get("/chat", response_class=HTMLResponse)
async def get_chat_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
