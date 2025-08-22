# auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Cookie, Response, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.models import User, Token, AppType
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
from app.captcha import verify_captcha
from pydantic import BaseModel, EmailStr
from typing import Optional
from app.services.apple_auth_service import AppleAuthService


router = APIRouter()


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


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


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class RegistrationWithOnboardingRequest(BaseModel):
    email: EmailStr
    password: str
    session_id: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class AppleSignInRequest(BaseModel):
    identity_token: str
    authorization_code: str
    user_full_name: Optional[str] = None
    user_email: Optional[str] = None


class AppleSignInResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user_id: int
    email: str
    auth_provider: str
    is_new_user: bool


@router.post("/register", response_model=TokenResponse)
@rate_limit("5/minute")
async def register(request: Request, user: UserCreate, db: Session = Depends(get_db), captcha: bool = Depends(verify_captcha)):
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


@router.post("/register-with-onboarding", response_model=TokenResponse)
@rate_limit("5/minute")
async def register_with_onboarding(
    request: Request,
    user_data: RegistrationWithOnboardingRequest,
    db: Session = Depends(get_db),
    captcha: bool = Depends(verify_captcha)
):
    """Register user with completed onboarding data"""
    # Check if email already exists
    db_user = db.query(User).filter(User.email == user_data.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Validate onboarding session
    try:
        from app.services.anonymous_onboarding_service import AnonymousOnboardingService
        anonymous_service = AnonymousOnboardingService()

        # Get and validate onboarding session
        session = await anonymous_service.get_session(user_data.session_id, db)
        if not session:
            raise HTTPException(
                status_code=400, detail="Invalid or expired onboarding session")

        if not session.is_completed:
            raise HTTPException(
                status_code=400, detail="Onboarding not completed")

    except Exception as e:
        logger.error(f"Error validating onboarding session: {e}")
        raise HTTPException(
            status_code=400, detail="Invalid onboarding session")

    # Create user account
    hashed_password = get_password_hash(user_data.password)
    new_user = User(email=user_data.email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Link onboarding session to user
    try:
        await anonymous_service.link_to_user(user_data.session_id, new_user.id, db)
    except Exception as e:
        logger.error(f"Failed to link onboarding session: {e}")
        # Don't fail registration if linking fails

    # Initialize onboarding for new user
    try:
        from app.services.onboarding_service import OnboardingService
        onboarding_service = OnboardingService()
        await onboarding_service.initialize_user_onboarding(new_user.id, db)
    except Exception as e:
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
        logger.error(
            f"Failed to initialize usage limits for user {new_user.id}: {e}")

    # Create tokens
    access_token = create_access_token(
        data={"sub": new_user.email, "user_id": new_user.id})
    refresh_token = create_refresh_token()

    token_entry = Token(user_id=new_user.id, access_token=access_token,
                        token_type="bearer", refresh_token=refresh_token)
    db.add(token_entry)
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return False
    return user


@router.post("/login", response_model=TokenSchema)
@rate_limit("5/minute")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db), captcha: bool = Depends(verify_captcha)):
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


@router.post("/apple-signin", response_model=AppleSignInResponse)
@rate_limit("5/minute")
async def apple_signin(
    request: Request,
    apple_request: AppleSignInRequest,
    db: Session = Depends(get_db)
):
    """Sign in or sign up with Apple ID"""
    try:
        # Initialize Apple auth service
        apple_service = AppleAuthService()

        # Verify Apple identity token
        decoded_token = await apple_service.verify_apple_token(apple_request.identity_token)
        if not decoded_token:
            raise HTTPException(status_code=400, detail="Invalid Apple token")

        # Extract user information
        user_info = apple_service.extract_user_info(decoded_token)
        apple_user_id = user_info["apple_user_id"]

        # Check if user already exists
        existing_user = db.query(User).filter(
            User.apple_user_id == apple_user_id
        ).first()

        if existing_user:
            # User exists, sign them in
            access_token = create_access_token(
                data={"sub": existing_user.email})
            refresh_token = create_refresh_token()

            # Create or update token record
            token_record = Token(
                user_id=existing_user.id,
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="bearer"
            )
            db.add(token_record)
            db.commit()

            return AppleSignInResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="bearer",
                user_id=existing_user.id,
                email=existing_user.email,
                auth_provider="apple",
                is_new_user=False
            )
        else:
            # New user, create account
            # Use email from Apple if provided, otherwise from request
            email = user_info.get("email") or apple_request.user_email
            if not email:
                raise HTTPException(
                    status_code=400, detail="Email is required")

            # Check if email is already registered with different provider
            email_user = db.query(User).filter(User.email == email).first()
            if email_user and email_user.auth_provider != "apple":
                raise HTTPException(
                    status_code=400,
                    detail="Email already registered with different authentication method"
                )

            # Create new user
            new_user = User(
                email=email,
                apple_user_id=apple_user_id,
                apple_email=user_info.get("email"),
                apple_full_name=apple_request.user_full_name,
                auth_provider="apple",
                email_verified=user_info.get("email_verified", False),
                app_type=AppType.MOBILE_CONSUMER  # Default for Apple Sign In
            )

            db.add(new_user)
            db.commit()
            db.refresh(new_user)

            # Initialize onboarding for new user
            try:
                from app.services.onboarding_service import OnboardingService
                onboarding_service = OnboardingService()
                await onboarding_service.initialize_user_onboarding(new_user.id, db)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(
                    f"Failed to initialize onboarding for Apple user {new_user.id}: {e}")

            # Initialize usage limits
            try:
                from app.services.usage_service import UsageService
                app_type = AppType.MOBILE_CONSUMER  # Default for Apple users
                UsageService.initialize_user_usage(new_user.id, app_type, db)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(
                    f"Failed to initialize usage limits for Apple user {new_user.id}: {e}")

            # Create tokens
            access_token = create_access_token(data={"sub": new_user.email})
            refresh_token = create_refresh_token()

            token_record = Token(
                user_id=new_user.id,
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="bearer"
            )
            db.add(token_record)
            db.commit()

            return AppleSignInResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="bearer",
                user_id=new_user.id,
                email=new_user.email,
                auth_provider="apple",
                is_new_user=True
            )

    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Apple signin error: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Apple authentication failed")

   # Make sure to export the function
__all__ = ["router", "get_current_user"]
