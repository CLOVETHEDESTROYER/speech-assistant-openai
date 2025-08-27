"""
Business Configuration API
Allows users to configure their SMS bot's business information and settings
"""

import logging
import os
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.db import get_db
from app.models import User, UserBusinessConfig, SMSPlan, ResponseTone
from app.auth import get_current_user
from app.services.user_sms_service import UserSMSService

router = APIRouter()
logger = logging.getLogger(__name__)


# Pydantic schemas for business configuration
class BusinessInfoUpdate(BaseModel):
    company_name: Optional[str] = Field(None, min_length=1, max_length=100)
    tagline: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    industry: Optional[str] = Field(None, max_length=100)
    website: Optional[str] = Field(None, max_length=200)


class ServicesUpdate(BaseModel):
    services: Optional[List[str]] = Field(None, min_items=1, max_items=20)


class PricingInfo(BaseModel):
    plan_name: str = Field(..., min_length=1, max_length=50)
    price: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=200)
    features: Optional[List[str]] = Field(None, max_items=10)


class PricingUpdate(BaseModel):
    pricing_plans: Optional[List[PricingInfo]] = Field(None, max_items=10)


class ContactInfo(BaseModel):
    email: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = Field(None, max_length=200)
    website: Optional[str] = Field(None, max_length=200)


class ContactUpdate(BaseModel):
    contact_info: ContactInfo


class BotPersonaUpdate(BaseModel):
    bot_name: Optional[str] = Field(None, min_length=1, max_length=50)
    bot_personality: Optional[str] = Field(None, max_length=500)
    response_tone: Optional[ResponseTone] = None
    custom_greeting: Optional[str] = Field(None, max_length=300)


class BusinessHours(BaseModel):
    start: str = Field(..., pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")  # HH:MM format
    end: str = Field(..., pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")


class BusinessHoursUpdate(BaseModel):
    timezone: Optional[str] = Field(None, max_length=50)
    monday: Optional[BusinessHours] = None
    tuesday: Optional[BusinessHours] = None
    wednesday: Optional[BusinessHours] = None
    thursday: Optional[BusinessHours] = None
    friday: Optional[BusinessHours] = None
    saturday: Optional[BusinessHours] = None
    sunday: Optional[BusinessHours] = None


class SMSSettingsUpdate(BaseModel):
    sms_enabled: Optional[bool] = None
    auto_responses_enabled: Optional[bool] = None
    calendar_integration_enabled: Optional[bool] = None
    lead_scoring_enabled: Optional[bool] = None


class CustomResponsesUpdate(BaseModel):
    pricing_response: Optional[str] = Field(None, max_length=500)
    demo_response: Optional[str] = Field(None, max_length=500)
    support_response: Optional[str] = Field(None, max_length=500)
    hours_response: Optional[str] = Field(None, max_length=500)
    fallback_response: Optional[str] = Field(None, max_length=500)


class CompleteBusinessConfig(BaseModel):
    """Complete business configuration for creating or updating all at once"""
    company_name: str = Field(..., min_length=1, max_length=100)
    tagline: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    industry: Optional[str] = Field(None, max_length=100)
    website: Optional[str] = Field(None, max_length=200)
    services: List[str] = Field(..., min_items=1, max_items=20)
    pricing_plans: Optional[List[PricingInfo]] = Field(None, max_items=10)
    contact_info: ContactInfo
    bot_name: str = Field(..., min_length=1, max_length=50)
    bot_personality: Optional[str] = Field(None, max_length=500)
    response_tone: ResponseTone = ResponseTone.PROFESSIONAL
    custom_greeting: Optional[str] = Field(None, max_length=300)
    business_hours: Optional[Dict[str, Any]] = None
    timezone: str = Field(default="America/Los_Angeles", max_length=50)
    sms_enabled: bool = True
    auto_responses_enabled: bool = True
    calendar_integration_enabled: bool = True
    lead_scoring_enabled: bool = True


# API Endpoints

@router.post("/business/config/complete")
async def setup_complete_business_config(
    config_data: CompleteBusinessConfig,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Setup or update complete business configuration"""
    try:
        # Check if config already exists
        existing_config = db.query(UserBusinessConfig).filter(
            UserBusinessConfig.user_id == current_user.id
        ).first()
        
        # Prepare data for database - exclude fields that don't map directly
        config_dict = config_data.dict(exclude={'pricing_plans'})
        
        # Handle business_hours separately if provided in the request
        if config_data.business_hours:
            config_dict["business_hours"] = config_data.business_hours
        
        # Convert pricing plans to pricing_info
        if config_data.pricing_plans:
            config_dict["pricing_info"] = [plan.dict() for plan in config_data.pricing_plans]
        
        # Convert contact info to JSON format
        config_dict["contact_info"] = config_data.contact_info.dict()
        
        if existing_config:
            # Update existing configuration
            for field, value in config_dict.items():
                if value is not None:
                    setattr(existing_config, field, value)
            
            config = existing_config
        else:
            # Create new configuration
            config = UserBusinessConfig(
                user_id=current_user.id,
                **config_dict
            )
            db.add(config)
        
        db.commit()
        db.refresh(config)
        
        # Get webhook URL (in production, use your actual domain)
        webhook_url = f"https://your-domain.com/sms/{current_user.id}/webhook"
        if os.getenv("DEVELOPMENT_MODE", "false").lower() == "true":
            webhook_url = f"http://localhost:5051/sms/{current_user.id}/webhook"
        
        return {
            "success": True,
            "message": "Business configuration saved successfully",
            "webhook_url": webhook_url,
            "user_id": current_user.id,
            "company_name": config.company_name,
            "bot_name": config.bot_name,
            "sms_enabled": config.sms_enabled
        }
        
    except Exception as e:
        logger.error(f"Error setting up business config for user {current_user.id}: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save configuration: {str(e)}")


@router.get("/business/config")
async def get_business_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current business configuration"""
    try:
        config = db.query(UserBusinessConfig).filter(
            UserBusinessConfig.user_id == current_user.id
        ).first()
        
        if not config:
            # Return default configuration structure
            webhook_url = f"https://your-domain.com/sms/{current_user.id}/webhook"
            if os.getenv("DEVELOPMENT_MODE", "false").lower() == "true":
                webhook_url = f"http://localhost:5051/sms/{current_user.id}/webhook"
            
            return {
                "configured": False,
                "webhook_url": webhook_url,
                "user_id": current_user.id,
                "message": "Business configuration not set up yet. Complete the setup to enable your SMS bot."
            }
        
        # Return full configuration
        webhook_url = f"https://your-domain.com/sms/{current_user.id}/webhook"
        if os.getenv("DEVELOPMENT_MODE", "false").lower() == "true":
            webhook_url = f"http://localhost:5051/sms/{current_user.id}/webhook"
        
        return {
            "configured": True,
            "webhook_url": webhook_url,
            "user_id": current_user.id,
            "company_name": config.company_name,
            "tagline": config.tagline,
            "description": config.description,
            "industry": config.industry,
            "website": config.website,
            "services": config.services,
            "pricing_info": config.pricing_info,
            "contact_info": config.contact_info,
            "bot_name": config.bot_name,
            "bot_personality": config.bot_personality,
            "response_tone": config.response_tone.value if config.response_tone else "professional",
            "custom_greeting": config.custom_greeting,
            "business_hours": config.business_hours,
            "timezone": config.timezone,
            "sms_enabled": config.sms_enabled,
            "auto_responses_enabled": config.auto_responses_enabled,
            "calendar_integration_enabled": config.calendar_integration_enabled,
            "lead_scoring_enabled": config.lead_scoring_enabled,
            "sms_plan": config.sms_plan.value,
            "monthly_conversation_limit": config.monthly_conversation_limit,
            "conversations_used_this_month": config.conversations_used_this_month,
            "total_conversations": config.total_conversations,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None
        }
        
    except Exception as e:
        logger.error(f"Error getting business config for user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get configuration")


@router.patch("/business/config/info")
async def update_business_info(
    info_update: BusinessInfoUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update basic business information"""
    return await _update_config_section(current_user.id, info_update, db)


@router.patch("/business/config/services")
async def update_services(
    services_update: ServicesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update services list"""
    return await _update_config_section(current_user.id, services_update, db)


@router.patch("/business/config/pricing")
async def update_pricing(
    pricing_update: PricingUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update pricing information"""
    # Convert pricing plans to JSON format
    if pricing_update.pricing_plans:
        pricing_data = {"pricing_info": [plan.dict() for plan in pricing_update.pricing_plans]}
        class PricingData(BaseModel):
            pricing_info: List[Dict[str, Any]]
        
        return await _update_config_section(current_user.id, PricingData(**pricing_data), db)
    
    return {"success": True, "message": "No pricing updates provided"}


@router.patch("/business/config/contact")
async def update_contact_info(
    contact_update: ContactUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update contact information"""
    # Convert to proper format
    contact_data = {"contact_info": contact_update.contact_info.dict()}
    class ContactData(BaseModel):
        contact_info: Dict[str, Any]
    
    return await _update_config_section(current_user.id, ContactData(**contact_data), db)


@router.patch("/business/config/bot")
async def update_bot_persona(
    bot_update: BotPersonaUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update bot persona and personality"""
    return await _update_config_section(current_user.id, bot_update, db)


@router.patch("/business/config/hours")
async def update_business_hours(
    hours_update: BusinessHoursUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update business hours"""
    # Convert business hours format
    hours_data = {}
    for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
        if hasattr(hours_update, day) and getattr(hours_update, day):
            day_hours = getattr(hours_update, day)
            hours_data[day] = {"start": day_hours.start, "end": day_hours.end}
        else:
            hours_data[day] = None
    
    update_data = {"business_hours": hours_data}
    if hours_update.timezone:
        update_data["timezone"] = hours_update.timezone
    
    class HoursData(BaseModel):
        business_hours: Dict[str, Any]
        timezone: Optional[str] = None
    
    return await _update_config_section(current_user.id, HoursData(**update_data), db)


@router.patch("/business/config/sms-settings")
async def update_sms_settings(
    sms_update: SMSSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update SMS bot settings"""
    return await _update_config_section(current_user.id, sms_update, db)


@router.get("/business/config/usage")
async def get_usage_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get SMS usage statistics"""
    try:
        user_sms_service = UserSMSService(current_user.id)
        usage_stats = user_sms_service.get_usage_stats(db)
        
        if "error" in usage_stats:
            raise HTTPException(status_code=500, detail=usage_stats["error"])
        
        return usage_stats
        
    except Exception as e:
        logger.error(f"Error getting usage stats for user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get usage statistics")


# Helper function
async def _update_config_section(user_id: int, update_data: BaseModel, db: Session):
    """Helper function to update specific configuration sections"""
    try:
        config = db.query(UserBusinessConfig).filter(
            UserBusinessConfig.user_id == user_id
        ).first()
        
        if not config:
            raise HTTPException(status_code=404, detail="Business configuration not found. Create it first.")
        
        # Update only provided fields
        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            if value is not None:
                setattr(config, field, value)
        
        db.commit()
        db.refresh(config)
        
        return {
            "success": True,
            "message": "Configuration updated successfully",
            "updated_fields": list(update_dict.keys())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating config section for user {user_id}: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update configuration: {str(e)}")
