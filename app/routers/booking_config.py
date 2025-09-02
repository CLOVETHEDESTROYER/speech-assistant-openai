"""
Employee-Based Booking Configuration API
Allows users to configure their booking limits based on number of employees
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.db import get_db
from app.models import User, UserBusinessConfig
from app.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

class BookingConfigUpdate(BaseModel):
    employee_count: int = Field(..., ge=1, le=100, description="Number of employees")
    max_concurrent_bookings: int = Field(..., ge=1, le=50, description="Maximum concurrent bookings per time slot")
    booking_policy: str = Field(..., pattern="^(strict|flexible|unlimited)$", description="Booking policy: strict (no overlap), flexible (up to limit), unlimited")
    allow_overbooking: bool = Field(default=False, description="Allow overbooking beyond limits")

class BookingConfigResponse(BaseModel):
    employee_count: int
    max_concurrent_bookings: int
    booking_policy: str
    allow_overbooking: bool
    message: str

@router.get("/booking/config", response_model=BookingConfigResponse)
async def get_booking_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current booking configuration"""
    try:
        business_config = db.query(UserBusinessConfig).filter(
            UserBusinessConfig.user_id == current_user.id
        ).first()
        
        if not business_config:
            # Return default values
            return BookingConfigResponse(
                employee_count=1,
                max_concurrent_bookings=1,
                booking_policy="strict",
                allow_overbooking=False,
                message="Using default booking configuration"
            )
        
        return BookingConfigResponse(
            employee_count=business_config.employee_count,
            max_concurrent_bookings=business_config.max_concurrent_bookings,
            booking_policy=business_config.booking_policy,
            allow_overbooking=business_config.allow_overbooking,
            message="Current booking configuration"
        )
        
    except Exception as e:
        logger.error(f"Error getting booking config for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get booking configuration")

@router.put("/booking/config", response_model=BookingConfigResponse)
async def update_booking_config(
    config_data: BookingConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update booking configuration"""
    try:
        # Validate business logic
        if config_data.booking_policy == "strict" and config_data.max_concurrent_bookings > 1:
            raise HTTPException(
                status_code=400, 
                detail="Strict policy only allows 1 concurrent booking per time slot"
            )
        
        if config_data.booking_policy == "flexible" and config_data.max_concurrent_bookings > config_data.employee_count * 2:
            raise HTTPException(
                status_code=400,
                detail="Flexible policy should not exceed 2x the number of employees"
            )
        
        # Get or create business config
        business_config = db.query(UserBusinessConfig).filter(
            UserBusinessConfig.user_id == current_user.id
        ).first()
        
        if not business_config:
            # Create new business config with defaults
            business_config = UserBusinessConfig(
                user_id=current_user.id,
                company_name=f"{current_user.email.split('@')[0].title()} Company",
                employee_count=config_data.employee_count,
                max_concurrent_bookings=config_data.max_concurrent_bookings,
                booking_policy=config_data.booking_policy,
                allow_overbooking=config_data.allow_overbooking
            )
            db.add(business_config)
        else:
            # Update existing config
            business_config.employee_count = config_data.employee_count
            business_config.max_concurrent_bookings = config_data.max_concurrent_bookings
            business_config.booking_policy = config_data.booking_policy
            business_config.allow_overbooking = config_data.allow_overbooking
        
        db.commit()
        db.refresh(business_config)
        
        logger.info(f"Updated booking config for user {current_user.id}: {config_data.employee_count} employees, {config_data.max_concurrent_bookings} max concurrent, {config_data.booking_policy} policy")
        
        return BookingConfigResponse(
            employee_count=business_config.employee_count,
            max_concurrent_bookings=business_config.max_concurrent_bookings,
            booking_policy=business_config.booking_policy,
            allow_overbooking=business_config.allow_overbooking,
            message="Booking configuration updated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating booking config for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update booking configuration")

@router.get("/booking/config/help")
async def get_booking_config_help():
    """Get help information about booking configuration options"""
    return {
        "booking_policies": {
            "strict": {
                "description": "No overlapping bookings allowed (1 booking per time slot)",
                "best_for": "Small businesses with 1 employee",
                "max_concurrent": 1
            },
            "flexible": {
                "description": "Allow multiple bookings up to the specified limit",
                "best_for": "Businesses with multiple employees who can handle concurrent appointments",
                "max_concurrent": "Up to 2x the number of employees"
            },
            "unlimited": {
                "description": "No limits on concurrent bookings",
                "best_for": "Large businesses with many staff members",
                "max_concurrent": "No limit"
            }
        },
        "examples": {
            "1_employee": {
                "employee_count": 1,
                "max_concurrent_bookings": 1,
                "booking_policy": "strict",
                "description": "Perfect for solo entrepreneurs"
            },
            "3_employees": {
                "employee_count": 3,
                "max_concurrent_bookings": 2,
                "booking_policy": "flexible",
                "description": "Can handle 2 concurrent appointments"
            },
            "10_employees": {
                "employee_count": 10,
                "max_concurrent_bookings": 5,
                "booking_policy": "flexible",
                "description": "Can handle 5 concurrent appointments"
            }
        }
    }
