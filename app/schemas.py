# schemas.py
from pydantic import BaseModel, EmailStr
from typing import Optional


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenSchema(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

    class Config:
        orm_mode = True


class TokenData(BaseModel):
    email: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str

    class Config:
        orm_mode = True


__all__ = ["UserCreate", "UserLogin", "TokenSchema", "TokenData"]
