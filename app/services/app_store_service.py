import os
import requests
import logging
import json
import hmac
import hashlib
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import User, UsageLimits, SubscriptionTier, SubscriptionStatus
from app.services.usage_service import UsageService

logger = logging.getLogger(__name__)


class AppStoreService:
    """Service for handling App Store in-app purchase validation and webhooks"""

    SANDBOX_URL = "https://sandbox.itunes.apple.com/verifyReceipt"
    PRODUCTION_URL = "https://buy.itunes.apple.com/verifyReceipt"

    @staticmethod
    def validate_receipt(receipt_data: str, is_sandbox: bool = False, retries: int = 0) -> Dict:
        """Validate App Store receipt with Apple's servers with retry cap to avoid loops"""
        if retries > 1:
            raise ValueError("Receipt validation retry limit exceeded")

        url = AppStoreService.SANDBOX_URL if is_sandbox else AppStoreService.PRODUCTION_URL
        shared_secret = os.getenv("APP_STORE_SHARED_SECRET")

        if not shared_secret:
            logger.error("APP_STORE_SHARED_SECRET not configured")
            raise ValueError("App Store shared secret not configured")

        payload = {
            "receipt-data": receipt_data,
            "password": shared_secret,
            "exclude-old-transactions": True
        }

        try:
            response = requests.post(url, json=payload, timeout=15)
            response.raise_for_status()
            result = response.json()

            logger.info(
                f"App Store validation response status: {result.get('status')}")

            if result.get("status") == 0:
                return result
            elif result.get("status") == 21007:
                # Sandbox receipt sent to production
                logger.warning(
                    "Sandbox receipt sent to production, retrying with sandbox")
                return AppStoreService.validate_receipt(receipt_data, is_sandbox=True, retries=retries + 1)
            elif result.get("status") == 21008:
                # Production receipt sent to sandbox
                logger.warning(
                    "Production receipt sent to sandbox, retrying with production")
                return AppStoreService.validate_receipt(receipt_data, is_sandbox=False, retries=retries + 1)
            else:
                logger.error(f"App Store validation failed: {result}")
                raise ValueError(
                    f"Receipt validation failed: {result.get('status')}")

        except requests.exceptions.RequestException as e:
            logger.error(
                f"Network error validating App Store receipt: {str(e)}")
            raise ValueError(f"Network error: {str(e)}")
        except Exception as e:
            logger.error(f"Error validating App Store receipt: {str(e)}")
            raise

    @staticmethod
    def extract_subscription_info(receipt_validation: Dict) -> Dict:
        """Extract subscription information from validated receipt"""
        try:
            latest_receipt_info = receipt_validation.get(
                "latest_receipt_info", [])
            if not latest_receipt_info:
                raise ValueError("No valid subscription found in receipt")

            # Get the latest transaction
            latest_transaction = latest_receipt_info[-1]

            # Extract key information
            subscription_info = {
                "product_id": latest_transaction.get("product_id"),
                "transaction_id": latest_transaction.get("transaction_id"),
                "original_transaction_id": latest_transaction.get("original_transaction_id"),
                "purchase_date": latest_transaction.get("purchase_date"),
                "expires_date": latest_transaction.get("expires_date"),
                "is_trial_period": latest_transaction.get("is_trial_period", "false") == "true",
                "is_in_intro_offer_period": latest_transaction.get("is_in_intro_offer_period", "false") == "true",
                "cancellation_date": latest_transaction.get("cancellation_date"),
                "web_order_line_item_id": latest_transaction.get("web_order_line_item_id")
            }

            logger.info(f"Extracted subscription info: {subscription_info}")
            return subscription_info

        except Exception as e:
            logger.error(f"Error extracting subscription info: {str(e)}")
            raise ValueError(f"Invalid receipt format: {str(e)}")

    @staticmethod
    def verify_webhook_signature(payload: str, signature: str) -> bool:
        """Verify App Store webhook signature"""
        webhook_secret = os.getenv("APP_STORE_WEBHOOK_SECRET")
        if not webhook_secret:
            logger.warning(
                "APP_STORE_WEBHOOK_SECRET not configured, skipping signature verification")
            return True

        try:
            expected_signature = hmac.new(
                webhook_secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {str(e)}")
            return False

    @staticmethod
    def process_subscription_notification(notification_data: Dict, db: Session) -> bool:
        """Process App Store subscription notification"""
        try:
            notification_type = notification_data.get("notification_type")
            signed_payload = notification_data.get("signedPayload")

            if not signed_payload:
                logger.error("No signed payload in notification")
                return False

            # Decode and verify the signed payload
            # In a real implementation, you'd decode the JWT and verify it
            # For now, we'll extract the data directly

            payload_data = notification_data.get("data", {})
            if not payload_data:
                logger.error("No data in notification payload")
                return False

            # Extract user and subscription info
            app_account_token = payload_data.get("appAccountToken")
            bundle_id = payload_data.get("bundleId")
            product_id = payload_data.get("productId")
            transaction_id = payload_data.get("transactionId")
            original_transaction_id = payload_data.get("originalTransactionId")

            logger.info(
                f"Processing {notification_type} notification for product {product_id}")

            # Find user by app account token (you may need to store this during registration)
            # For now, we'll need to implement a way to map app account tokens to users

            if notification_type == "RENEWAL":
                return AppStoreService._handle_renewal(
                    original_transaction_id, product_id, payload_data, db
                )
            elif notification_type == "CANCEL":
                return AppStoreService._handle_cancellation(
                    original_transaction_id, db
                )
            elif notification_type == "BILLING_ISSUE":
                return AppStoreService._handle_billing_issue(
                    original_transaction_id, db
                )
            elif notification_type == "PRICE_INCREASE":
                return AppStoreService._handle_price_increase(
                    original_transaction_id, payload_data, db
                )
            else:
                logger.info(
                    f"Unhandled notification type: {notification_type}")
                return True

        except Exception as e:
            logger.error(
                f"Error processing subscription notification: {str(e)}")
            return False

    @staticmethod
    def _handle_renewal(original_transaction_id: str, product_id: str, payload_data: Dict, db: Session) -> bool:
        """Handle subscription renewal"""
        try:
            # Find usage limits by original transaction ID
            usage = db.query(UsageLimits).filter(
                UsageLimits.app_store_transaction_id == original_transaction_id
            ).first()

            if not usage:
                logger.warning(
                    f"No usage limits found for transaction {original_transaction_id}")
                return False

            # Update subscription end date
            expires_date_str = payload_data.get("expiresDate")
            if expires_date_str:
                # Convert Apple's date format to datetime
                expires_date = datetime.fromisoformat(
                    expires_date_str.replace('Z', '+00:00'))
                usage.subscription_end_date = expires_date
                usage.subscription_status = SubscriptionStatus.ACTIVE
                usage.next_payment_date = expires_date
                usage.updated_at = datetime.utcnow()

                db.commit()
                logger.info(f"Renewed subscription for user {usage.user_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error handling renewal: {str(e)}")
            db.rollback()
            return False

    @staticmethod
    def _handle_cancellation(original_transaction_id: str, db: Session) -> bool:
        """Handle subscription cancellation"""
        try:
            usage = db.query(UsageLimits).filter(
                UsageLimits.app_store_transaction_id == original_transaction_id
            ).first()

            if not usage:
                logger.warning(
                    f"No usage limits found for transaction {original_transaction_id}")
                return False

            usage.subscription_status = SubscriptionStatus.CANCELLED
            usage.updated_at = datetime.utcnow()

            db.commit()
            logger.info(f"Cancelled subscription for user {usage.user_id}")
            return True

        except Exception as e:
            logger.error(f"Error handling cancellation: {str(e)}")
            db.rollback()
            return False

    @staticmethod
    def _handle_billing_issue(original_transaction_id: str, db: Session) -> bool:
        """Handle billing issues"""
        try:
            usage = db.query(UsageLimits).filter(
                UsageLimits.app_store_transaction_id == original_transaction_id
            ).first()

            if not usage:
                logger.warning(
                    f"No usage limits found for transaction {original_transaction_id}")
                return False

            usage.subscription_status = SubscriptionStatus.BILLING_RETRY
            usage.updated_at = datetime.utcnow()

            db.commit()
            logger.info(f"Marked billing issue for user {usage.user_id}")
            return True

        except Exception as e:
            logger.error(f"Error handling billing issue: {str(e)}")
            db.rollback()
            return False

    @staticmethod
    def _handle_price_increase(original_transaction_id: str, payload_data: Dict, db: Session) -> bool:
        """Handle price increase notifications"""
        try:
            usage = db.query(UsageLimits).filter(
                UsageLimits.app_store_transaction_id == original_transaction_id
            ).first()

            if not usage:
                logger.warning(
                    f"No usage limits found for transaction {original_transaction_id}")
                return False

            # Log the price increase for tracking
            logger.info(
                f"Price increase notification for user {usage.user_id}")

            # You might want to send an email notification to the user here
            # For now, we'll just log it

            return True

        except Exception as e:
            logger.error(f"Error handling price increase: {str(e)}")
            return False
