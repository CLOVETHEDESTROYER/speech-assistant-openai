# schemas.py
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    id: int
    email: EmailStr
    name: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class TokenData(BaseModel):
    email: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

    class Config:
        orm_mode = True


class TokenSchema(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

    class Config:
        orm_mode = True


__all__ = ["UserCreate", "UserLogin", "TokenSchema", "TokenData"]
