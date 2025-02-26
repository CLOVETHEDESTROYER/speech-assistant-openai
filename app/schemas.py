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


class RealtimeSessionCreate(BaseModel):
    scenario: str
    user_id: Optional[int] = None


class RealtimeSessionResponse(BaseModel):
    session_id: str
    ice_servers: list
    created_at: str


class SignalingMessage(BaseModel):
    type: str
    sdp: Optional[str] = None
    candidate: Optional[dict] = None
    session_id: str


class SignalingResponse(BaseModel):
    type: str
    sdp: Optional[str] = None
    ice_servers: Optional[list] = None
    error: Optional[str] = None


class ConversationResponse(BaseModel):
    id: int
    call_sid: str
    phone_number: Optional[str]
    direction: str
    scenario: str
    transcript: Optional[str]
    created_at: str
    user_id: Optional[int]

    class Config:
        orm_mode = True


__all__ = ["UserCreate", "UserLogin", "TokenSchema", "TokenData", "RealtimeSessionCreate",
           "RealtimeSessionResponse", "SignalingMessage", "SignalingResponse", "ConversationResponse"]
