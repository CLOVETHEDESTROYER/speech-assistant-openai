from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import get_current_user
from app.models import User, UserOnboardingStatus
from app.services.twilio_service import TwilioPhoneService
from app.services.onboarding_service import OnboardingService
from pydantic import BaseModel
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/twilio", tags=["twilio"])

# Pydantic models


class PhoneNumberProvisionRequest(BaseModel):
    phone_number: str


class PhoneNumberSearchRequest(BaseModel):
    area_code: Optional[str] = None
    limit: int = 10


class TwilioAccountResponse(BaseModel):
    accountSid: str
    balance: str
    status: str
    currency: str


class PhoneNumberResponse(BaseModel):
    sid: str
    phoneNumber: str
    friendlyName: str
    capabilities: dict
    dateCreated: str
    isActive: bool


# Initialize services
twilio_service = TwilioPhoneService()
onboarding_service = OnboardingService()


@router.get("/account", response_model=TwilioAccountResponse)
async def get_twilio_account(current_user: User = Depends(get_current_user)):
    """Get Twilio account information"""
    try:
        account_info = await twilio_service.get_account_info()
        return TwilioAccountResponse(**account_info)
    except Exception as e:
        logger.error(f"Error fetching Twilio account: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to fetch account information")


@router.post("/search-numbers")
async def search_available_numbers(
    request: PhoneNumberSearchRequest,
    current_user: User = Depends(get_current_user)
):
    """Search for available phone numbers"""
    try:
        numbers = await twilio_service.search_available_numbers(
            area_code=request.area_code,
            limit=request.limit
        )
        return {"availableNumbers": numbers}
    except Exception as e:
        logger.error(f"Error searching numbers: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to search available numbers")


@router.post("/provision-number")
async def provision_phone_number(
    request: PhoneNumberProvisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Provision a new phone number for the user"""
    try:
        # Check if user already has a phone number (limit for now)
        existing_numbers = await twilio_service.get_user_numbers(current_user.id, db)
        if len(existing_numbers) >= 3:  # Limit to 3 numbers per user
            raise HTTPException(
                status_code=400,
                detail="Maximum number of phone numbers reached (3)"
            )

        # Provision the number
        user_phone = await twilio_service.provision_number(
            request.phone_number,
            current_user.id,
            db
        )

        # Update onboarding status
        onboarding = db.query(UserOnboardingStatus).filter(
            UserOnboardingStatus.user_id == current_user.id
        ).first()

        if onboarding and not onboarding.phone_number_setup:
            onboarding.phone_number_setup = True
            onboarding.current_step = "calendar"
            db.commit()

        return {
            "phoneNumber": user_phone.phone_number,
            "sid": user_phone.twilio_sid,
            "message": f"Phone number {user_phone.phone_number} provisioned successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error provisioning phone number: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to provision phone number: {str(e)}")


@router.get("/user-numbers", response_model=List[PhoneNumberResponse])
async def get_user_phone_numbers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get phone numbers assigned to the current user"""
    try:
        numbers = await twilio_service.get_user_numbers(current_user.id, db)
        return [PhoneNumberResponse(**num) for num in numbers]
    except Exception as e:
        logger.error(f"Error fetching user phone numbers: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to fetch phone numbers")


@router.delete("/release-number/{phone_number}")
async def release_phone_number(
    phone_number: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Release a phone number"""
    try:
        success = await twilio_service.release_number(phone_number, current_user.id, db)
        if success:
            return {"message": f"Phone number {phone_number} released successfully"}
        else:
            raise HTTPException(
                status_code=400, detail="Failed to release phone number")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error releasing phone number {phone_number}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to release phone number: {str(e)}")


@router.get("/user-primary-number")
async def get_user_primary_number(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the user's primary phone number for making calls"""
    try:
        primary_number = twilio_service.get_user_primary_number(
            current_user.id, db)
        if not primary_number:
            raise HTTPException(
                status_code=404,
                detail="No phone number available. Please provision a phone number first."
            )

        return {
            "phoneNumber": primary_number.phone_number,
            "sid": primary_number.twilio_sid,
            "friendlyName": primary_number.friendly_name,
            "isActive": primary_number.is_active
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting primary number: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get primary phone number")
