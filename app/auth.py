# auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Cookie, Response, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.models import User, Token
from app.schemas import TokenData, UserCreate, UserLogin, TokenResponse, TokenSchema
from app.db import get_db
from app.utils import (
    decode_token,
    get_password_hash,
    verify_password,
    create_access_token,
)
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import os
import uuid
import json
from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from datetime import timedelta
from app.limiter import rate_limit


router = APIRouter()


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def decode_access_token(token: str):
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.email == token_data.email).first()
    if user is None:
        raise credentials_exception
    return user


def create_refresh_token():
    return str(uuid.uuid4())


@router.post("/register", response_model=TokenResponse)
@rate_limit("5/minute")
async def register(request: Request, user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = get_password_hash(user.password)
    new_user = User(email=user.email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Initialize onboarding for new user
    try:
        from app.services.onboarding_service import OnboardingService
        onboarding_service = OnboardingService()
        await onboarding_service.initialize_user_onboarding(new_user.id, db)
    except Exception as e:
        # Log the error but don't fail registration
        import logging
        logger = logging.getLogger(__name__)
        logger.error(
            f"Failed to initialize onboarding for user {new_user.id}: {e}")

    # Initialize usage limits based on app type
    try:
        from app.services.usage_service import UsageService
        from app.models import AppType

        # Detect app type from request
        app_type = UsageService.detect_app_type_from_request(request)
        UsageService.initialize_user_usage(new_user.id, app_type, db)

    except Exception as e:
        # Log the error but don't fail registration
        import logging
        logger = logging.getLogger(__name__)
        logger.error(
            f"Failed to initialize usage limits for user {new_user.id}: {e}")

    access_token = create_access_token(
        data={"sub": new_user.email, "user_id": new_user.id})
    refresh_token = create_refresh_token()

    token_entry = Token(user_id=new_user.id, access_token=access_token,
                        token_type="bearer", refresh_token=refresh_token)
    db.add(token_entry)
    db.commit()

    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return False
    return user


@router.post("/login", response_model=TokenSchema)
@rate_limit("5/minute")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


@router.post("/refresh", response_model=TokenResponse)
@rate_limit("10/minute")
async def refresh_token_route(request: Request, token: str = Cookie(None), db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(status_code=401, detail="Refresh token missing")
    decoded = decode_token(token)
    if not decoded:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    token_entry = db.query(Token).filter(
        Token.refresh_token == token, Token.is_valid == True).first()
    if not token_entry:
        raise HTTPException(
            status_code=401, detail="Refresh token invalid or expired")

    # Invalidate the old refresh token
    token_entry.is_valid = False
    db.commit()

    # Issue new tokens
    new_access_token = create_access_token(
        data={"sub": token_entry.user.email, "user_id": token_entry.user_id})
    new_refresh_token = create_refresh_token()

    new_token_entry = Token(user_id=token_entry.user_id,
                            refresh_token=new_refresh_token)
    db.add(new_token_entry)
    db.commit()

    response = {"access_token": new_access_token,
                "refresh_token": new_refresh_token, "token_type": "bearer"}
    return response


@router.post("/logout")
async def logout(response: Response):
    response = JSONResponse(content={"detail": "Logged out successfully"})
    response.delete_cookie(key="access_token")
    return response

   # Make sure to export the function
__all__ = ["router", "get_current_user"]
