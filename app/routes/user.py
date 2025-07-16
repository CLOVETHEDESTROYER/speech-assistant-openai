# app/routes/user.py
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import get_current_user
from app.models import User
from app.schemas import UserRead
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["user"])


class UpdateNameRequest(BaseModel):
    name: str


@router.get("/me", response_model=UserRead)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return current_user


@router.post("/update-name")
async def update_user_name(
    name: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user's name"""
    try:
        # Update user's name
        current_user.name = name
        db.commit()
        db.refresh(current_user)
        
        logger.info(f"Updated name for user {current_user.email} to: {name}")
        
        return {
            "message": "Name updated successfully",
            "name": current_user.name
        }
        
    except Exception as e:
        logger.error(f"Error updating name for user {current_user.id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update name"
        )


# Alternative endpoint for compatibility with iOS app
@router.post("/update-user-name") 
async def update_user_name_alt(
    name: str = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user's name - alternative endpoint for compatibility"""
    try:
        # Update user's name
        current_user.name = name.strip() if isinstance(name, str) else str(name).strip()
        db.commit()
        db.refresh(current_user)
        
        logger.info(f"Updated name for user {current_user.email} to: {current_user.name}")
        
        return {
            "message": "Name updated successfully",
            "name": current_user.name,
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"Error updating name for user {current_user.id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update name"
        ) 