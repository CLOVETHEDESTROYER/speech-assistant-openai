# auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Cookie, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.models import User, Token, UsageLimits, AppType
from app.schemas import TokenData, UserCreate, UserLogin, TokenResponse, TokenSchema
from app.db import get_db
from app.utils import (
    decode_token,
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token
)
from app.services.usage_service import UsageService
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import os
import uuid
import json
from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


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


@router.post("/register", response_model=TokenResponse)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    """Register a new user with proper usage limits initialization"""
    try:
        # Check if user already exists
        db_user = db.query(User).filter(User.email == user.email).first()
        if db_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Email already registered"
            )
        
        # Create new user
        hashed_password = get_password_hash(user.password)
        new_user = User(email=user.email, hashed_password=hashed_password)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        # Initialize usage limits for mobile app (default)
        usage_limits = UsageService.initialize_user_usage(
            new_user.id, AppType.MOBILE, db)
        
        # Create tokens
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": new_user.email, "user_id": new_user.id},
            expires_delta=access_token_expires
        )
        refresh_token = create_refresh_token(
            data={"sub": new_user.email, "user_id": new_user.id}
        )
        
        # Store token in database
        token_entry = Token(
            user_id=new_user.id, 
            access_token=access_token,
            token_type="bearer", 
            refresh_token=refresh_token
        )
        db.add(token_entry)
        db.commit()
        
        logger.info(f"New user registered: {new_user.email} (ID: {new_user.id})")
        
        return TokenResponse(
            access_token=access_token, 
            refresh_token=refresh_token, 
            token_type="bearer"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed. Please try again."
        )


def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return False
    return user


@router.post("/login", response_model=TokenSchema)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """User login endpoint"""
    try:
        user = authenticate_user(db, form_data.username, form_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email, "user_id": user.id}, 
            expires_delta=access_token_expires
        )
        refresh_token = create_refresh_token(
            data={"sub": user.email, "user_id": user.id}
        )
        
        # Update or create token entry
        token_entry = db.query(Token).filter(Token.user_id == user.id).first()
        if token_entry:
            token_entry.access_token = access_token
            token_entry.refresh_token = refresh_token
        else:
            token_entry = Token(
                user_id=user.id,
                access_token=access_token,
                token_type="bearer",
                refresh_token=refresh_token
            )
            db.add(token_entry)
        
        db.commit()
        
        logger.info(f"User logged in: {user.email}")
        
        return TokenSchema(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed. Please try again."
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(refresh_token: str, db: Session = Depends(get_db)):
    """Refresh access token using refresh token"""
    try:
        # Verify refresh token
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        user_id: int = payload.get("user_id")
        
        if email is None or user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        # Check if refresh token exists in database
        token_entry = db.query(Token).filter(
            Token.refresh_token == refresh_token,
            Token.user_id == user_id
        ).first()
        
        if not token_entry:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        # Create new access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        new_access_token = create_access_token(
            data={"sub": email, "user_id": user_id},
            expires_delta=access_token_expires
        )
        
        # Update token in database
        token_entry.access_token = new_access_token
        db.commit()
        
        return TokenResponse(
            access_token=new_access_token,
            refresh_token=refresh_token,
            token_type="bearer"
        )
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Logout user by invalidating tokens"""
    try:
        # Remove user's tokens from database
        db.query(Token).filter(Token.user_id == current_user.id).delete()
        db.commit()
        
        logger.info(f"User logged out: {current_user.email}")
        
        return {"message": "Successfully logged out"}
        
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )

   # Make sure to export the function
__all__ = ["router", "get_current_user"]
