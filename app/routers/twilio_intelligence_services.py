from fastapi import APIRouter, Depends, HTTPException, Body, Request
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import get_current_user
from app.utils.twilio_helpers import with_twilio_retry
from app.limiter import rate_limit
from app.models import User
from app.services.twilio_client import get_twilio_client
from app import config
from twilio.base.exceptions import TwilioException
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/intelligence-services")
@with_twilio_retry(max_retries=3)
async def list_intelligence_services(
    page_size: int = 20,
    page_token: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    List all Intelligence Services for the Twilio account.
    """
    try:
        params = {"limit": page_size}
        if page_token:
            params["page_token"] = page_token
            
        services = get_twilio_client().intelligence.v2.services.list(**params)
        
        formatted_services = [
            {
                "sid": service.sid,
                "friendly_name": service.friendly_name,
                "auto_transcribe": service.auto_transcribe,
                "auto_redaction": service.auto_redaction,
                "data_logging": service.data_logging,
                "webhook_url": service.webhook_url,
                "webhook_http_method": service.webhook_http_method,
                "date_created": str(service.date_created) if service.date_created else None,
                "date_updated": str(service.date_updated) if service.date_updated else None
            }
            for service in services
        ]
        
        return {
            "services": formatted_services,
            "count": len(formatted_services)
        }
        
    except TwilioException as e:
        logger.error(f"Twilio API error listing services: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Twilio API error: {str(e)}")
    except Exception as e:
        logger.error(f"Error listing intelligence services: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/intelligence-services/{service_sid}")
@with_twilio_retry(max_retries=3)
async def get_intelligence_service(
    service_sid: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get details of a specific Intelligence Service.
    """
    try:
        service = get_twilio_client().intelligence.v2.services(service_sid).fetch()
        
        return {
            "sid": service.sid,
            "friendly_name": service.friendly_name,
            "auto_transcribe": service.auto_transcribe,
            "auto_redaction": service.auto_redaction,
            "data_logging": service.data_logging,
            "webhook_url": service.webhook_url,
            "webhook_http_method": service.webhook_http_method,
            "date_created": str(service.date_created) if service.date_created else None,
            "date_updated": str(service.date_updated) if service.date_updated else None
        }
        
    except TwilioException as e:
        logger.error(f"Twilio API error fetching service {service_sid}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Twilio API error: {str(e)}")
    except Exception as e:
        logger.error(f"Error fetching intelligence service {service_sid}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/intelligence-services")
@rate_limit("5/minute")
@with_twilio_retry(max_retries=3)
async def create_intelligence_service(
    request: Request,
    friendly_name: str = Body(..., description="Friendly name for the service"),
    auto_transcribe: bool = Body(True, description="Enable automatic transcription"),
    auto_redaction: bool = Body(True, description="Enable automatic PII redaction"),
    data_logging: bool = Body(True, description="Enable data logging"),
    webhook_url: Optional[str] = Body(None, description="Webhook URL for real-time updates"),
    webhook_http_method: str = Body("POST", description="HTTP method for webhook"),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new Intelligence Service for conversation analysis.
    """
    try:
        service_data = {
            "friendly_name": friendly_name,
            "auto_transcribe": auto_transcribe,
            "auto_redaction": auto_redaction,
            "data_logging": data_logging
        }
        
        if webhook_url:
            service_data["webhook_url"] = webhook_url
            service_data["webhook_http_method"] = webhook_http_method
        
        service = get_twilio_client().intelligence.v2.services.create(**service_data)
        
        logger.info(f"Created Intelligence Service: {service.sid} - {friendly_name}")
        
        return {
            "status": "success",
            "service_sid": service.sid,
            "friendly_name": service.friendly_name,
            "message": "Intelligence Service created successfully"
        }
        
    except TwilioException as e:
        logger.error(f"Twilio API error creating service: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Twilio API error: {str(e)}")
    except Exception as e:
        logger.error(f"Error creating intelligence service: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/intelligence-services/{service_sid}")
@rate_limit("10/minute")
@with_twilio_retry(max_retries=3)
async def update_intelligence_service(
    service_sid: str,
    request: Request,
    friendly_name: Optional[str] = Body(None, description="New friendly name"),
    auto_transcribe: Optional[bool] = Body(None, description="Enable/disable automatic transcription"),
    auto_redaction: Optional[bool] = Body(None, description="Enable/disable automatic PII redaction"),
    data_logging: Optional[bool] = Body(None, description="Enable/disable data logging"),
    webhook_url: Optional[str] = Body(None, description="New webhook URL"),
    webhook_http_method: Optional[str] = Body(None, description="New webhook HTTP method"),
    current_user: User = Depends(get_current_user)
):
    """
    Update an existing Intelligence Service.
    """
    try:
        update_data = {}
        
        if friendly_name is not None:
            update_data["friendly_name"] = friendly_name
        if auto_transcribe is not None:
            update_data["auto_transcribe"] = auto_transcribe
        if auto_redaction is not None:
            update_data["auto_redaction"] = auto_redaction
        if data_logging is not None:
            update_data["data_logging"] = data_logging
        if webhook_url is not None:
            update_data["webhook_url"] = webhook_url
        if webhook_http_method is not None:
            update_data["webhook_http_method"] = webhook_http_method
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No update data provided")
        
        service = get_twilio_client().intelligence.v2.services(service_sid).update(**update_data)
        
        logger.info(f"Updated Intelligence Service: {service_sid}")
        
        return {
            "status": "success",
            "service_sid": service.sid,
            "friendly_name": service.friendly_name,
            "message": "Intelligence Service updated successfully"
        }
        
    except TwilioException as e:
        logger.error(f"Twilio API error updating service {service_sid}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Twilio API error: {str(e)}")
    except Exception as e:
        logger.error(f"Error updating intelligence service {service_sid}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/intelligence-services/{service_sid}")
@rate_limit("5/minute")
@with_twilio_retry(max_retries=3)
async def delete_intelligence_service(
    service_sid: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Delete an Intelligence Service.
    """
    try:
        get_twilio_client().intelligence.v2.services(service_sid).delete()
        
        logger.info(f"Deleted Intelligence Service: {service_sid}")
        
        return {
            "status": "success",
            "message": f"Intelligence Service {service_sid} deleted successfully"
        }
        
    except TwilioException as e:
        logger.error(f"Twilio API error deleting service {service_sid}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Twilio API error: {str(e)}")
    except Exception as e:
        logger.error(f"Error deleting intelligence service {service_sid}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/intelligence-operators")
@with_twilio_retry(max_retries=3)
async def list_language_operators(
    current_user: User = Depends(get_current_user)
):
    """
    List available Language Operators for transcript analysis.
    """
    try:
        operators = get_twilio_client().intelligence.v2.operators.list()
        
        formatted_operators = [
            {
                "sid": operator.sid,
                "friendly_name": operator.friendly_name,
                "description": operator.description,
                "operator_type": operator.operator_type,
                "config": operator.config,
                "date_created": str(operator.date_created) if operator.date_created else None,
                "date_updated": str(operator.date_updated) if operator.date_updated else None
            }
            for operator in operators
        ]
        
        return {
            "operators": formatted_operators,
            "count": len(formatted_operators)
        }
        
    except TwilioException as e:
        logger.error(f"Twilio API error listing operators: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Twilio API error: {str(e)}")
    except Exception as e:
        logger.error(f"Error listing language operators: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/intelligence-services/{service_sid}/attach-operator")
@rate_limit("10/minute")
@with_twilio_retry(max_retries=3)
async def attach_operator_to_service(
    service_sid: str,
    request: Request,
    operator_sid: str = Body(..., description="SID of the operator to attach"),
    current_user: User = Depends(get_current_user)
):
    """
    Attach a Language Operator to an Intelligence Service for transcript analysis.
    """
    try:
        # Get current service to retrieve existing operators
        service = get_twilio_client().intelligence.v2.services(service_sid).fetch()
        
        # Get current attached operators
        current_operators = getattr(service, 'read_only_attached_operator_sids', []) or []
        
        # Add new operator if not already attached
        if operator_sid not in current_operators:
            current_operators.append(operator_sid)
        
        # Update service with new operator list
        updated_service = get_twilio_client().intelligence.v2.services(service_sid).update(
            read_only_attached_operator_sids=current_operators
        )
        
        logger.info(f"Attached operator {operator_sid} to service {service_sid}")
        
        return {
            "status": "success",
            "service_sid": service_sid,
            "operator_sid": operator_sid,
            "attached_operators": current_operators,
            "message": "Operator attached successfully"
        }
        
    except TwilioException as e:
        logger.error(f"Twilio API error attaching operator {operator_sid} to service {service_sid}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Twilio API error: {str(e)}")
    except Exception as e:
        logger.error(f"Error attaching operator to service: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/intelligence-services/{service_sid}/detach-operator/{operator_sid}")
@rate_limit("10/minute")
@with_twilio_retry(max_retries=3)
async def detach_operator_from_service(
    service_sid: str,
    operator_sid: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Detach a Language Operator from an Intelligence Service.
    """
    try:
        # Get current service to retrieve existing operators
        service = get_twilio_client().intelligence.v2.services(service_sid).fetch()
        
        # Get current attached operators
        current_operators = getattr(service, 'read_only_attached_operator_sids', []) or []
        
        # Remove operator if attached
        if operator_sid in current_operators:
            current_operators.remove(operator_sid)
        
        # Update service with updated operator list
        updated_service = get_twilio_client().intelligence.v2.services(service_sid).update(
            read_only_attached_operator_sids=current_operators
        )
        
        logger.info(f"Detached operator {operator_sid} from service {service_sid}")
        
        return {
            "status": "success",
            "service_sid": service_sid,
            "operator_sid": operator_sid,
            "attached_operators": current_operators,
            "message": "Operator detached successfully"
        }
        
    except TwilioException as e:
        logger.error(f"Twilio API error detaching operator {operator_sid} from service {service_sid}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Twilio API error: {str(e)}")
    except Exception as e:
        logger.error(f"Error detaching operator from service: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
