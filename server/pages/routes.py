from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import jwt, JWTError
from pathlib import Path
from server.utils.template_engine import templates
import uuid
import time

from server.auth.auth import SECRET_KEY, ALGORITHM, create_access_token

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def get_root_page(request: Request):
    token = request.cookies.get("access_token")

    if not token:
        # Generate a unique guest username with timestamp
        guest_id = str(uuid.uuid4())[:8]
        guest_username = f"guest_{guest_id}_{int(time.time())}"

        # Create guest token (no database entry needed)
        access_token = create_access_token(
            data={"sub": guest_username, "is_guest": True})

        # Create response with the token as a cookie
        response = templates.TemplateResponse(
            "index.html", {"request": request})
        response.set_cookie(key="access_token",
                            value=access_token, httponly=False, max_age=3600)
        return response

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        is_guest = payload.get("is_guest", False)

        if not username:
            raise JWTError()

        # Both regular users and guests are allowed to access the chat
        # The username will include "guest_" prefix for guest users
    except JWTError:
        # If token is invalid, generate a new guest user
        guest_id = str(uuid.uuid4())[:8]
        guest_username = f"guest_{guest_id}_{int(time.time())}"

        # Create guest token (no database entry needed)
        access_token = create_access_token(
            data={"sub": guest_username, "is_guest": True})

        # Create response with the token as a cookie
        response = templates.TemplateResponse(
            "index.html", {"request": request})
        response.set_cookie(key="access_token",
                            value=access_token, httponly=False, max_age=3600)
        return response

    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/chat", response_class=HTMLResponse)
async def get_chat_page(request: Request):
    token = request.cookies.get("access_token")

    if not token:
        # Generate a unique guest username with timestamp
        guest_id = str(uuid.uuid4())[:8]
        guest_username = f"guest_{guest_id}_{int(time.time())}"

        # Create guest token (no database entry needed)
        access_token = create_access_token(
            data={"sub": guest_username, "is_guest": True})

        # Create response with the token as a cookie
        response = templates.TemplateResponse(
            "index.html", {"request": request})
        response.set_cookie(key="access_token",
                            value=access_token, httponly=False, max_age=3600)
        return response

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        is_guest = payload.get("is_guest", False)

        if not username:
            raise JWTError()

        # Both regular users and guests are allowed to access the chat
        # The username will include "guest_" prefix for guest users
    except JWTError:
        # If token is invalid, generate a new guest user
        guest_id = str(uuid.uuid4())[:8]
        guest_username = f"guest_{guest_id}_{int(time.time())}"

        # Create guest token (no database entry needed)
        access_token = create_access_token(
            data={"sub": guest_username, "is_guest": True})

        # Create response with the token as a cookie
        response = templates.TemplateResponse(
            "index.html", {"request": request})
        response.set_cookie(key="access_token",
                            value=access_token, httponly=False, max_age=3600)
        return response

    return templates.TemplateResponse("index.html", {"request": request})
