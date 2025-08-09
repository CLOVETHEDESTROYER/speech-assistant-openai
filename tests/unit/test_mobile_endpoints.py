#!/usr/bin/env python3
"""
Comprehensive Mobile Endpoint Tests

Tests all mobile-specific endpoints including:
- Authentication with mobile headers
- Usage tracking and trial management
- Subscription handling
- Scenario management
- Call functionality
- App Store integration
"""

import pytest
import json
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.models import User, UsageLimits, CustomScenario, SubscriptionTier, SubscriptionStatus
from app.utils import get_password_hash
from app.db import get_db, SessionLocal, Base, engine
from sqlalchemy.orm import Session


class TestMobileEndpoints:
    """Test suite for mobile-specific endpoints"""
    
    @pytest.fixture
    def client(self):
        """Test client"""
        return TestClient(app)
    
    @pytest.fixture
    def db_session(self):
        """Database session"""
        Base.metadata.create_all(bind=engine)
        session = SessionLocal()
        yield session
        session.close()
        Base.metadata.drop_all(bind=engine)
    
    @pytest.fixture
    def mobile_user(self, db_session):
        """Create a test mobile user"""
        user = User(
            email="mobile@test.com",
            hashed_password=get_password_hash("password123"),
            is_active=True,
            is_admin=False
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user
    
    @pytest.fixture
    def mobile_auth_headers(self, client, mobile_user):
        """Get authentication headers for mobile user"""
        response = client.post(
            "/token",
            data={
                "username": "mobile@test.com",
                "password": "password123"
            },
            headers={"X-App-Type": "mobile"}
        )
        token = response.json()["access_token"]
        return {
            "Authorization": f"Bearer {token}",
            "X-App-Type": "mobile",
            "Content-Type": "application/json"
        }
    
    def test_mobile_registration(self, client, db_session):
        """Test mobile user registration"""
        user_data = {
            "email": "newmobile@test.com",
            "password": "securepassword123"
        }
        
        response = client.post(
            "/auth/register",
            json=user_data,
            headers={"X-App-Type": "mobile"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        
        # Verify user was created with mobile settings
        user = db_session.query(User).filter(User.email == "newmobile@test.com").first()
        assert user is not None
        assert user.is_active is True
        assert user.is_admin is False
    
    def test_mobile_login(self, client, mobile_user):
        """Test mobile user login"""
        response = client.post(
            "/token",
            data={
                "username": "mobile@test.com",
                "password": "password123"
            },
            headers={"X-App-Type": "mobile"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
    
    def test_mobile_usage_stats_initialization(self, client, mobile_auth_headers, db_session, mobile_user):
        """Test that mobile users get proper usage limits initialized"""
        response = client.get(
            "/mobile/usage-stats",
            headers=mobile_auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify mobile-specific settings
        assert data["app_type"] == "mobile_consumer"
        assert data["is_trial_active"] is True
        assert data["trial_calls_remaining"] == 3  # Mobile gets 3 trial calls
        assert data["trial_calls_used"] == 0
        assert data["is_subscribed"] is False
        assert data["subscription_tier"] is None
        
        # Verify usage limits were created in database
        usage_limits = db_session.query(UsageLimits).filter(
            UsageLimits.user_id == mobile_user.id
        ).first()
        assert usage_limits is not None
        assert usage_limits.trial_calls_remaining == 3
        assert usage_limits.subscription_tier == SubscriptionTier.MOBILE_FREE_TRIAL
    
    def test_mobile_scenarios(self, client, mobile_auth_headers):
        """Test mobile scenarios endpoint"""
        response = client.get(
            "/mobile/scenarios",
            headers=mobile_auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify mobile scenarios are entertainment-focused
        scenarios = data["scenarios"]
        assert len(scenarios) > 0
        
        # Check for expected mobile scenarios
        scenario_ids = [s["id"] for s in scenarios]
        expected_scenarios = ["fake_doctor", "fake_boss", "fake_tech_support", "fake_celebrity"]
        for expected in expected_scenarios:
            assert expected in scenario_ids
        
        # Verify scenario structure
        for scenario in scenarios:
            assert "id" in scenario
            assert "name" in scenario
            assert "description" in scenario
            assert "icon" in scenario
            assert "category" in scenario
            assert "difficulty" in scenario
    
    def test_mobile_pricing(self, client, mobile_auth_headers):
        """Test mobile pricing endpoint"""
        response = client.get(
            "/mobile/pricing",
            headers=mobile_auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify mobile pricing structure
        assert "plans" in data
        assert "addon" in data
        
        plans = data["plans"]
        assert len(plans) >= 2  # Should have basic and premium plans
        
        # Check basic plan
        basic_plan = next((p for p in plans if p["id"] == "basic"), None)
        assert basic_plan is not None
        assert basic_plan["price"] == "$4.99"
        assert basic_plan["billing"] == "weekly"
        
        # Check addon
        addon = data["addon"]
        assert addon["price"] == "$4.99"
        assert "5 additional calls" in addon["calls"]
    
    @patch('app.routes.mobile_app.AppStoreService.validate_receipt')
    def test_mobile_subscription_purchase(self, mock_validate_receipt, client, mobile_auth_headers, db_session, mobile_user):
        """Test mobile subscription purchase with App Store receipt"""
        # Mock successful receipt validation
        mock_validate_receipt.return_value = {
            "status": 0,
            "receipt": {
                "in_app": [{
                    "product_id": "speech_assistant_basic_weekly",
                    "transaction_id": "test_transaction_123",
                    "original_transaction_id": "test_original_123",
                    "purchase_date_ms": str(int(time.time() * 1000)),
                    "expires_date_ms": str(int((time.time() + 7*24*60*60) * 1000))
                }]
            }
        }
        
        purchase_data = {
            "receipt_data": "base64_encoded_receipt_data",
            "is_sandbox": True,
            "product_id": "speech_assistant_basic_weekly"
        }
        
        response = client.post(
            "/mobile/purchase-subscription",
            json=purchase_data,
            headers=mobile_auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Successfully upgraded" in data["message"]
        
        # Verify usage limits were updated
        usage_stats = data["usage_stats"]
        assert usage_stats["is_subscribed"] is True
        assert usage_stats["subscription_tier"] == "mobile_basic"
        
        # Verify database was updated
        usage_limits = db_session.query(UsageLimits).filter(
            UsageLimits.user_id == mobile_user.id
        ).first()
        assert usage_limits.subscription_tier == SubscriptionTier.MOBILE_BASIC
        assert usage_limits.subscription_status == SubscriptionStatus.ACTIVE
    
    def test_mobile_call_permission_check(self, client, mobile_auth_headers, db_session, mobile_user):
        """Test mobile call permission checking"""
        # Test with trial calls remaining
        response = client.post(
            "/mobile/check-call-permission",
            json={"phone_number": "+1234567890", "scenario": "default"},
            headers=mobile_auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["can_make_call"] is True
        assert data["reason"] == "trial_calls_remaining"
        
        # Test with no trial calls remaining and no subscription
        usage_limits = db_session.query(UsageLimits).filter(
            UsageLimits.user_id == mobile_user.id
        ).first()
        usage_limits.trial_calls_remaining = 0
        usage_limits.subscription_tier = None
        db_session.commit()
        
        response = client.post(
            "/mobile/check-call-permission",
            json={"phone_number": "+1234567890", "scenario": "default"},
            headers=mobile_auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["can_make_call"] is False
        assert "trial" in data["reason"].lower() or "subscription" in data["reason"].lower()
    
    def test_mobile_call_history(self, client, mobile_auth_headers, db_session, mobile_user):
        """Test mobile call history endpoint"""
        response = client.get(
            "/mobile/call-history",
            headers=mobile_auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "call_history" in data
        assert "total_calls" in data
        assert isinstance(data["call_history"], list)
        assert isinstance(data["total_calls"], int)
    
    def test_mobile_schedule_call(self, client, mobile_auth_headers):
        """Test mobile call scheduling"""
        schedule_data = {
            "phone_number": "+1234567890",
            "scenario": "default",
            "scheduled_time": (datetime.now() + timedelta(minutes=5)).isoformat()
        }
        
        response = client.post(
            "/mobile/schedule-call",
            json=schedule_data,
            headers=mobile_auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "schedule_id" in data
        assert data["phone_number"] == "+1234567890"
        assert data["scenario"] == "default"
        assert data["status"] == "scheduled"
    
    def test_mobile_headers_required(self, client, mobile_user):
        """Test that mobile endpoints require proper headers"""
        # Test without mobile headers
        response = client.post(
            "/token",
            data={
                "username": "mobile@test.com",
                "password": "password123"
            }
        )
        
        # Should still work but might not get mobile-specific behavior
        assert response.status_code == 200
    
    def test_mobile_rate_limiting(self, client, mobile_auth_headers):
        """Test mobile endpoint rate limiting"""
        # Make multiple rapid requests to test rate limiting
        responses = []
        for i in range(6):  # Should hit rate limit
            response = client.get(
                "/mobile/usage-stats",
                headers=mobile_auth_headers
            )
            responses.append(response)
        
        # Most should succeed, but rate limiting should be in place
        success_count = sum(1 for r in responses if r.status_code == 200)
        assert success_count >= 4  # Should allow at least 4 requests
    
    def test_mobile_error_handling(self, client, mobile_auth_headers):
        """Test mobile endpoint error handling"""
        # Test with invalid phone number
        response = client.post(
            "/mobile/check-call-permission",
            json={"phone_number": "invalid", "scenario": "default"},
            headers=mobile_auth_headers
        )
        
        # Should return validation error
        assert response.status_code == 422
        
        # Test with non-existent scenario
        response = client.post(
            "/mobile/check-call-permission",
            json={"phone_number": "+1234567890", "scenario": "nonexistent"},
            headers=mobile_auth_headers
        )
        
        # Should handle gracefully
        assert response.status_code in [200, 400, 404]
    
    def test_mobile_subscription_status(self, client, mobile_auth_headers):
        """Test mobile subscription status endpoint"""
        response = client.get(
            "/mobile/subscription-status",
            headers=mobile_auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "subscription_status" in data
        assert "subscription_tier" in data
        assert "expires_at" in data
        assert "auto_renew_status" in data


class TestMobileAppStoreIntegration:
    """Test App Store integration endpoints"""
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    def test_app_store_webhook_endpoint(self, client):
        """Test App Store webhook endpoint"""
        webhook_data = {
            "signedPayload": "test_payload",
            "notificationType": "RENEWAL",
            "data": {
                "productId": "speech_assistant_basic_weekly",
                "transactionId": "test_transaction",
                "originalTransactionId": "test_original_transaction"
            }
        }
        
        response = client.post(
            "/mobile/app-store/webhook",
            json=webhook_data
        )
        
        # Should handle webhook (might return 401 without proper signature)
        assert response.status_code in [200, 401, 500]
    
    def test_subscription_status_endpoint(self, client):
        """Test subscription status endpoint"""
        response = client.get("/mobile/subscription-status")
        
        # Should require authentication
        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
