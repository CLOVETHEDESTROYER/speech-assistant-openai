#!/usr/bin/env python3
"""
Comprehensive test runner for Twilio Intelligence API implementation.
This script tests all the new Twilio Intelligence endpoints and features.
"""

import asyncio
import sys
import os
import json
from datetime import datetime
from typing import Dict, Any, List

# Add the app directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '.'))

from app.services.twilio_intelligence import TwilioIntelligenceService
from app.services.conversational_intelligence import ConversationalIntelligenceService
from app.services.twilio_client import get_twilio_client
from app import config

# Test configuration
TEST_CONFIG = {
    "test_recording_sid": "RE1234567890abcdef1234567890abcdef",  # Mock recording SID
    "test_transcript_sid": "GT1234567890abcdef1234567890abcdef",  # Mock transcript SID
    "test_service_sid": "IS1234567890abcdef1234567890abcdef",     # Mock service SID
    "test_operator_sid": "LY1234567890abcdef1234567890abcdef",    # Mock operator SID
}


class TwilioIntelligenceTestRunner:
    """Comprehensive test runner for Twilio Intelligence features."""
    
    def __init__(self):
        self.results = {
            "test_timestamp": datetime.utcnow().isoformat(),
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "test_results": []
        }
    
    def log_test_result(self, test_name: str, passed: bool, message: str = "", details: Dict = None):
        """Log the result of a test."""
        self.results["total_tests"] += 1
        if passed:
            self.results["passed_tests"] += 1
            status = "✅ PASS"
        else:
            self.results["failed_tests"] += 1
            status = "❌ FAIL"
        
        test_result = {
            "test_name": test_name,
            "status": status,
            "passed": passed,
            "message": message,
            "details": details or {}
        }
        
        self.results["test_results"].append(test_result)
        print(f"{status} {test_name}: {message}")
    
    async def test_twilio_intelligence_service(self):
        """Test the TwilioIntelligenceService class."""
        print("\n🧪 Testing TwilioIntelligenceService...")
        
        try:
            # Test service initialization
            service = TwilioIntelligenceService()
            self.log_test_result(
                "TwilioIntelligenceService Initialization",
                True,
                "Service initialized successfully"
            )
            
            # Test service configuration
            has_voice_intelligence_sid = hasattr(service, 'voice_intelligence_sid')
            self.log_test_result(
                "Voice Intelligence SID Configuration",
                has_voice_intelligence_sid,
                f"Voice Intelligence SID configured: {has_voice_intelligence_sid}"
            )
            
        except Exception as e:
            self.log_test_result(
                "TwilioIntelligenceService Initialization",
                False,
                f"Service initialization failed: {str(e)}"
            )
    
    async def test_conversational_intelligence_service(self):
        """Test the ConversationalIntelligenceService class."""
        print("\n🧠 Testing ConversationalIntelligenceService...")
        
        try:
            # Test service initialization
            service = ConversationalIntelligenceService()
            self.log_test_result(
                "ConversationalIntelligenceService Initialization",
                True,
                "Service initialized successfully"
            )
            
            # Test sentiment analysis method
            test_sentences = [
                {"text": "This is a great product!", "confidence": 0.9},
                {"text": "I love this service.", "confidence": 0.8},
                {"text": "This is terrible.", "confidence": 0.7}
            ]
            
            sentiment_result = await service._analyze_sentiment(test_sentences)
            has_sentiment_analysis = "overall_sentiment" in sentiment_result
            
            self.log_test_result(
                "Sentiment Analysis",
                has_sentiment_analysis,
                f"Sentiment analysis working: {has_sentiment_analysis}",
                {"sentiment_result": sentiment_result}
            )
            
            # Test topic extraction
            topic_result = await service._extract_topics(test_sentences)
            has_topic_extraction = "detected_topics" in topic_result
            
            self.log_test_result(
                "Topic Extraction",
                has_topic_extraction,
                f"Topic extraction working: {has_topic_extraction}",
                {"topic_result": topic_result}
            )
            
            # Test insights generation
            insights_result = await service._generate_insights(test_sentences)
            has_insights = "conversation_metrics" in insights_result
            
            self.log_test_result(
                "Conversation Insights",
                has_insights,
                f"Insights generation working: {has_insights}",
                {"insights_result": insights_result}
            )
            
        except Exception as e:
            self.log_test_result(
                "ConversationalIntelligenceService",
                False,
                f"Service testing failed: {str(e)}"
            )
    
    async def test_twilio_client_connection(self):
        """Test Twilio client connection and configuration."""
        print("\n📞 Testing Twilio Client Connection...")
        
        try:
            client = get_twilio_client()
            self.log_test_result(
                "Twilio Client Initialization",
                client is not None,
                "Twilio client initialized successfully"
            )
            
            # Test account info retrieval (this will fail in test environment, but we can check the attempt)
            try:
                account = client.api.accounts(client.account_sid).fetch()
                self.log_test_result(
                    "Twilio Account Connection",
                    True,
                    f"Connected to account: {account.friendly_name}"
                )
            except Exception as e:
                # This is expected in test environment
                self.log_test_result(
                    "Twilio Account Connection",
                    False,
                    f"Account connection failed (expected in test): {str(e)}"
                )
            
        except Exception as e:
            self.log_test_result(
                "Twilio Client Connection",
                False,
                f"Client connection failed: {str(e)}"
            )
    
    async def test_configuration_validation(self):
        """Test that all required configuration is present."""
        print("\n⚙️ Testing Configuration...")
        
        required_configs = [
            ("TWILIO_ACCOUNT_SID", config.TWILIO_ACCOUNT_SID),
            ("TWILIO_AUTH_TOKEN", config.TWILIO_AUTH_TOKEN),
            ("TWILIO_VOICE_INTELLIGENCE_SID", config.TWILIO_VOICE_INTELLIGENCE_SID),
        ]
        
        for config_name, config_value in required_configs:
            has_config = config_value is not None and config_value != ""
            self.log_test_result(
                f"Configuration: {config_name}",
                has_config,
                f"{config_name} configured: {has_config}"
            )
    
    async def test_api_endpoint_structure(self):
        """Test that API endpoints are properly structured."""
        print("\n🔗 Testing API Endpoint Structure...")
        
        # Test that router files exist and can be imported
        try:
            from app.routers.twilio_intelligence_services import router as intelligence_router
            self.log_test_result(
                "Intelligence Services Router",
                True,
                "Intelligence services router imported successfully"
            )
        except Exception as e:
            self.log_test_result(
                "Intelligence Services Router",
                False,
                f"Failed to import intelligence services router: {str(e)}"
            )
        
        try:
            from app.routers.conversational_intelligence import router as conversational_router
            self.log_test_result(
                "Conversational Intelligence Router",
                True,
                "Conversational intelligence router imported successfully"
            )
        except Exception as e:
            self.log_test_result(
                "Conversational Intelligence Router",
                False,
                f"Failed to import conversational intelligence router: {str(e)}"
            )
        
        try:
            from app.routers.twilio_transcripts import router as transcripts_router
            self.log_test_result(
                "Twilio Transcripts Router",
                True,
                "Twilio transcripts router imported successfully"
            )
        except Exception as e:
            self.log_test_result(
                "Twilio Transcripts Router",
                False,
                f"Failed to import transcripts router: {str(e)}"
            )
    
    async def test_mock_data_processing(self):
        """Test data processing with mock data."""
        print("\n📊 Testing Mock Data Processing...")
        
        try:
            # Mock transcript data
            mock_transcript_data = {
                "sid": TEST_CONFIG["test_transcript_sid"],
                "status": "completed",
                "duration": 120,
                "language_code": "en-US",
                "sentences": [
                    {
                        "text": "Hello, I'd like to schedule an appointment.",
                        "speaker": 0,
                        "start_time": 0.0,
                        "end_time": 3.5,
                        "confidence": 0.95
                    },
                    {
                        "text": "I'd be happy to help you with that. What time works best?",
                        "speaker": 1,
                        "start_time": 4.0,
                        "end_time": 7.2,
                        "confidence": 0.92
                    },
                    {
                        "text": "How about tomorrow at 2 PM?",
                        "speaker": 0,
                        "start_time": 8.0,
                        "end_time": 11.0,
                        "confidence": 0.88
                    }
                ]
            }
            
            # Test conversational intelligence with mock data
            service = ConversationalIntelligenceService()
            
            # Test sentiment analysis
            sentiment = await service._analyze_sentiment(mock_transcript_data["sentences"])
            self.log_test_result(
                "Mock Sentiment Analysis",
                "overall_sentiment" in sentiment,
                f"Sentiment analysis completed: {sentiment.get('overall_sentiment', 'unknown')}"
            )
            
            # Test topic extraction
            topics = await service._extract_topics(mock_transcript_data["sentences"])
            self.log_test_result(
                "Mock Topic Extraction",
                "detected_topics" in topics,
                f"Topics detected: {topics.get('detected_topics', [])}"
            )
            
            # Test insights generation
            insights = await service._generate_insights(mock_transcript_data["sentences"])
            self.log_test_result(
                "Mock Insights Generation",
                "conversation_metrics" in insights,
                f"Insights generated: {len(insights)} metrics"
            )
            
        except Exception as e:
            self.log_test_result(
                "Mock Data Processing",
                False,
                f"Mock data processing failed: {str(e)}"
            )
    
    async def run_all_tests(self):
        """Run all tests."""
        print("🚀 Starting Comprehensive Twilio Intelligence API Tests")
        print("=" * 60)
        
        await self.test_configuration_validation()
        await self.test_twilio_client_connection()
        await self.test_api_endpoint_structure()
        await self.test_twilio_intelligence_service()
        await self.test_conversational_intelligence_service()
        await self.test_mock_data_processing()
        
        # Print summary
        print("\n" + "=" * 60)
        print("📋 TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {self.results['total_tests']}")
        print(f"✅ Passed: {self.results['passed_tests']}")
        print(f"❌ Failed: {self.results['failed_tests']}")
        print(f"Success Rate: {(self.results['passed_tests'] / self.results['total_tests'] * 100):.1f}%")
        
        # Save detailed results
        results_file = f"twilio_intelligence_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n📄 Detailed results saved to: {results_file}")
        
        return self.results


async def main():
    """Main test runner function."""
    test_runner = TwilioIntelligenceTestRunner()
    results = await test_runner.run_all_tests()
    
    # Exit with error code if any tests failed
    if results['failed_tests'] > 0:
        print(f"\n⚠️  {results['failed_tests']} tests failed. Check the results above.")
        sys.exit(1)
    else:
        print("\n🎉 All tests passed! Twilio Intelligence API implementation is ready.")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
