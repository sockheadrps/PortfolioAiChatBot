from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from server.db.db import get_db
from server.auth.auth import authenticate_user, create_access_token, register_user
from server.utils.template_engine import templates


router = APIRouter()

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": user.username})
    response = JSONResponse(content={"access_token": access_token})
    response.set_cookie(key="access_token", value=access_token, httponly=False, max_age=3600)
    return response

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@router.post("/register")
async def register(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = register_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Username already exists")
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token}

@router.post("/guest-login")
async def guest_login():
    # Generate a unique guest username with timestamp
    import uuid
    import time
    guest_id = str(uuid.uuid4())[:8]
    guest_username = f"guest_{guest_id}_{int(time.time())}"
    
    # Create guest token (no database entry needed)
    access_token = create_access_token(data={"sub": guest_username, "is_guest": True})
    response = JSONResponse(content={"access_token": access_token, "username": guest_username})
    response.set_cookie(key="access_token", value=access_token, httponly=False, max_age=3600)
    return response

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("access_token")
    return response
