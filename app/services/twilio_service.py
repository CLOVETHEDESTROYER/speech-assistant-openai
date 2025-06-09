from twilio.rest import Client
from sqlalchemy.orm import Session
from app.models import UserPhoneNumber, User
import os
import logging
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


class TwilioPhoneService:
    def __init__(self):
        self.account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.client = Client(self.account_sid, self.auth_token)
        self.public_url = os.getenv('PUBLIC_URL', '').strip()

        if not self.account_sid or not self.auth_token:
            raise ValueError(
                "Twilio credentials are not set in environment variables")

    async def get_account_info(self) -> Dict:
        """Get Twilio account information"""
        try:
            balance = self.client.balance.fetch()
            account = self.client.api.accounts(self.account_sid).fetch()

            return {
                "accountSid": self.account_sid,
                "balance": balance.balance,
                "status": account.status,
                "currency": balance.currency
            }
        except Exception as e:
            logger.error(f"Error fetching Twilio account: {e}")
            raise

    async def search_available_numbers(self, area_code: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """Search for available phone numbers"""
        try:
            search_params = {
                'limit': limit,
                'voice_enabled': True,
                'sms_enabled': True
            }

            if area_code:
                search_params['area_code'] = area_code

            available_numbers = self.client.available_phone_numbers(
                'US').local.list(**search_params)

            return [
                {
                    "phoneNumber": number.phone_number,
                    "friendlyName": number.friendly_name,
                    "locality": number.locality,
                    "region": number.region,
                    "capabilities": {
                        "voice": getattr(number, 'voice_enabled', True),
                        "sms": getattr(number, 'sms_enabled', True)
                    }
                }
                for number in available_numbers
            ]
        except Exception as e:
            logger.error(f"Error searching numbers: {e}")
            raise

    async def provision_number(self, phone_number: str, user_id: int, db: Session) -> UserPhoneNumber:
        """Provision a phone number for a user"""
        try:
            # Purchase the number from Twilio
            webhook_url = f"https://{self.public_url}/incoming-call/default"

            purchased_number = self.client.incoming_phone_numbers.create(
                phone_number=phone_number,
                voice_url=webhook_url,
                voice_method='POST',
                status_callback_url=f"https://{self.public_url}/phone-status-callback",
                status_callback_method='POST'
            )

            # Store in database
            user_phone = UserPhoneNumber(
                user_id=user_id,
                phone_number=purchased_number.phone_number,
                twilio_sid=purchased_number.sid,
                friendly_name=purchased_number.friendly_name,
                voice_capable=True,
                sms_capable=True
            )

            db.add(user_phone)
            db.commit()
            db.refresh(user_phone)

            logger.info(
                f"Provisioned phone number {phone_number} for user {user_id}")
            return user_phone

        except Exception as e:
            logger.error(f"Error provisioning number {phone_number}: {e}")
            db.rollback()
            raise

    async def release_number(self, phone_number: str, user_id: int, db: Session) -> bool:
        """Release a user's phone number"""
        try:
            # Get user's phone number
            user_number = db.query(UserPhoneNumber).filter(
                UserPhoneNumber.user_id == user_id,
                UserPhoneNumber.phone_number == phone_number,
                UserPhoneNumber.is_active == True
            ).first()

            if not user_number:
                raise ValueError("Phone number not found or not owned by user")

            # Release from Twilio
            self.client.incoming_phone_numbers(user_number.twilio_sid).delete()

            # Mark as inactive in database
            user_number.is_active = False
            db.commit()

            logger.info(
                f"Released phone number {phone_number} for user {user_id}")
            return True

        except Exception as e:
            logger.error(f"Error releasing number {phone_number}: {e}")
            db.rollback()
            raise

    async def get_user_numbers(self, user_id: int, db: Session) -> List[Dict]:
        """Get all active phone numbers for a user"""
        try:
            user_numbers = db.query(UserPhoneNumber).filter(
                UserPhoneNumber.user_id == user_id,
                UserPhoneNumber.is_active == True
            ).all()

            # Enrich with current Twilio data
            enriched_numbers = []
            for user_number in user_numbers:
                try:
                    twilio_number = self.client.incoming_phone_numbers(
                        user_number.twilio_sid).fetch()

                    enriched_numbers.append({
                        "sid": twilio_number.sid,
                        "phoneNumber": twilio_number.phone_number,
                        "friendlyName": twilio_number.friendly_name or "No name set",
                        "capabilities": {
                            "voice": True,  # We only provision voice-capable numbers
                            "sms": True
                        },
                        "dateCreated": user_number.date_provisioned.isoformat(),
                        "isActive": user_number.is_active
                    })
                except Exception as e:
                    logger.warning(
                        f"Could not fetch Twilio data for {user_number.phone_number}: {e}")
                    # Fallback to database data
                    enriched_numbers.append({
                        "sid": user_number.twilio_sid,
                        "phoneNumber": user_number.phone_number,
                        "friendlyName": user_number.friendly_name or "No name set",
                        "capabilities": {
                            "voice": user_number.voice_capable,
                            "sms": user_number.sms_capable
                        },
                        "dateCreated": user_number.date_provisioned.isoformat(),
                        "isActive": user_number.is_active
                    })

            return enriched_numbers

        except Exception as e:
            logger.error(f"Error fetching user numbers: {e}")
            raise

    def get_user_primary_number(self, user_id: int, db: Session) -> Optional[UserPhoneNumber]:
        """Get the primary (first active) phone number for a user"""
        try:
            return db.query(UserPhoneNumber).filter(
                UserPhoneNumber.user_id == user_id,
                UserPhoneNumber.is_active == True,
                UserPhoneNumber.voice_capable == True
            ).first()
        except Exception as e:
            logger.error(
                f"Error getting primary number for user {user_id}: {e}")
            return None
