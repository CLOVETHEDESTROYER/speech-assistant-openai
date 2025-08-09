#!/usr/bin/env python3
"""
Setup Test Environment for Speech Assistant Security Testing

This script sets up the development environment with proper configuration
for comprehensive security testing.
"""

import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path


def create_test_env_file():
    """Create a test environment file with secure defaults"""
    test_env_content = """# Test Environment Configuration
# This file is used for security testing

# Development mode
DEVELOPMENT_MODE=true

# OpenAI Configuration (use test key)
OPENAI_API_KEY=sk-test-key-for-testing-only

# Twilio Configuration (use test credentials)
TWILIO_ACCOUNT_SID=ACtestaccountsid123
TWILIO_AUTH_TOKEN=testauthtoken123
TWILIO_PHONE_NUMBER=+1234567890

# Twilio Voice Intelligence (disabled for testing)
TWILIO_VOICE_INTELLIGENCE_SID=
USE_TWILIO_VOICE_INTELLIGENCE=false
ENABLE_PII_REDACTION=true

# Database Configuration (use test database)
DATABASE_URL=sqlite:///./test_app.db

# Server Configuration
PORT=5051
PUBLIC_URL=http://localhost:5051

# JWT Authentication (use test secret)
SECRET_KEY=test-secret-key-for-development-only-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Logging Configuration
LOG_LEVEL=DEBUG
LOG_DIR=logs
LOG_MAX_SIZE_MB=10
LOG_BACKUP_COUNT=5

# Security Headers (enabled for testing)
ENABLE_SECURITY_HEADERS=true
CONTENT_SECURITY_POLICY=default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self' wss: https:;
ENABLE_HSTS=true
HSTS_MAX_AGE=31536000
XSS_PROTECTION=true
CONTENT_TYPE_OPTIONS=true
FRAME_OPTIONS=DENY

# Voice Configuration
VOICE_ID=alloy
VOICE_MODEL=tts-1

# Session Configuration
MAX_SESSION_DURATION=3600
SESSION_CLEANUP_INTERVAL=300

# CAPTCHA Configuration (disabled for testing)
RECAPTCHA_SECRET_KEY=
RECAPTCHA_SITE_KEY=

# Rate Limiting (enabled for testing)
ENABLE_RATE_LIMITING=true
"""

    with open('test.env', 'w') as f:
        f.write(test_env_content)

    print("✅ Created test.env file")


def install_dependencies():
    """Install required dependencies for testing"""
    print("📦 Installing dependencies...")

    try:
        # Install pytest and testing dependencies
        subprocess.run([
            sys.executable, "-m", "pip", "install",
            "pytest", "pytest-asyncio", "pytest-mock", "httpx", "requests"
        ], check=True)
        print("✅ Dependencies installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False

    return True


def setup_database():
    """Setup test database"""
    print("🗄️ Setting up test database...")

    try:
        # Import and setup database
        from app.db import engine, Base
        from app.models import User
        from app.utils import get_password_hash

        # Create tables
        Base.metadata.create_all(bind=engine)

        # Create test admin user
        from sqlalchemy.orm import Session
        db = Session(engine)

        # Check if test user already exists
        test_user = db.query(User).filter(
            User.email == "admin@test.com").first()
        if not test_user:
            test_user = User(
                email="admin@test.com",
                hashed_password=get_password_hash("AdminTest123!"),
                is_active=True,
                is_admin=True
            )
            db.add(test_user)
            db.commit()
            print("✅ Created test admin user: admin@test.com / AdminTest123!")
        else:
            print("✅ Test admin user already exists")

        db.close()

    except Exception as e:
        print(f"❌ Failed to setup database: {e}")
        return False

    return True


def create_test_scripts():
    """Create test scripts for easy testing"""

    # Create run_tests.py
    run_tests_content = '''#!/usr/bin/env python3
"""
Run all tests for the Speech Assistant
"""

import subprocess
import sys
import os

def run_security_tests():
    """Run comprehensive security tests"""
    print("🔒 Running Security Tests...")
    try:
        result = subprocess.run([sys.executable, "test_security_comprehensive.py"], 
                              capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("Errors:", result.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Security tests failed: {e}")
        return False

def run_unit_tests():
    """Run unit tests"""
    print("🧪 Running Unit Tests...")
    try:
        result = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-v"], 
                              capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("Errors:", result.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Unit tests failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Starting Test Suite")
    print("=" * 50)
    
    # Set test environment
    os.environ['DEVELOPMENT_MODE'] = 'true'
    
    # Run tests
    security_passed = run_security_tests()
    unit_passed = run_unit_tests()
    
    print("=" * 50)
    print("📊 Test Results:")
    print(f"Security Tests: {'✅ PASSED' if security_passed else '❌ FAILED'}")
    print(f"Unit Tests: {'✅ PASSED' if unit_passed else '❌ FAILED'}")
    
    if security_passed and unit_passed:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️ Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
'''

    with open('run_tests.py', 'w') as f:
        f.write(run_tests_content)

    # Make executable
    os.chmod('run_tests.py', 0o755)

    # Create start_dev_server.py
    start_dev_content = '''#!/usr/bin/env python3
"""
Start development server for testing
"""

import uvicorn
import os
import sys

def main():
    """Start the development server"""
    # Set development environment
    os.environ['DEVELOPMENT_MODE'] = 'true'
    
    print("🚀 Starting Development Server...")
    print("📱 Server will be available at: http://localhost:8000")
    print("📚 API docs will be available at: http://localhost:8000/docs")
    print("🛑 Press Ctrl+C to stop the server")
    
    try:
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
'''

    with open('start_dev_server.py', 'w') as f:
        f.write(start_dev_content)

    # Make executable
    os.chmod('start_dev_server.py', 0o755)

    print("✅ Created test scripts: run_tests.py, start_dev_server.py")


def create_test_data():
    """Create test data for comprehensive testing"""
    print("📝 Creating test data...")

    try:
        from app.db import SessionLocal
        from app.models import CustomScenario, User

        db = SessionLocal()

        # Get test user
        test_user = db.query(User).filter(
            User.email == "admin@test.com").first()

        if test_user:
            # Create test custom scenarios
            test_scenarios = [
                {
                    "user_id": test_user.id,
                    "persona": "You are a helpful customer service representative.",
                    "prompt": "Help customers with their inquiries professionally.",
                    "voice_type": "alloy",
                    "temperature": 0.7
                },
                {
                    "user_id": test_user.id,
                    "persona": "You are a friendly sales agent.",
                    "prompt": "Help customers find the right products.",
                    "voice_type": "nova",
                    "temperature": 0.8
                }
            ]

            for scenario_data in test_scenarios:
                # Generate a unique scenario_id
                import uuid
                scenario_data["scenario_id"] = str(uuid.uuid4())

                existing = db.query(CustomScenario).filter(
                    CustomScenario.user_id == test_user.id,
                    CustomScenario.scenario_id == scenario_data["scenario_id"]
                ).first()

                if not existing:
                    scenario = CustomScenario(**scenario_data)
                    db.add(scenario)

            db.commit()
            print("✅ Created test custom scenarios")
        else:
            print("⚠️ Test user not found, skipping test data creation")

        db.close()

    except Exception as e:
        print(f"❌ Failed to create test data: {e}")


def main():
    """Main setup function"""
    print("🔧 Setting up Test Environment for Speech Assistant")
    print("=" * 60)

    # Check if we're in the right directory
    if not os.path.exists('app'):
        print("❌ Error: Please run this script from the project root directory")
        return 1

    # Create test environment file
    create_test_env_file()

    # Install dependencies
    if not install_dependencies():
        return 1

    # Setup database
    if not setup_database():
        return 1

    # Create test scripts
    create_test_scripts()

    # Create test data
    create_test_data()

    print("\n" + "=" * 60)
    print("🎉 Test Environment Setup Complete!")
    print("\n📋 Next Steps:")
    print("1. Run security tests: python test_security_comprehensive.py")
    print("2. Run all tests: python run_tests.py")
    print("3. Start dev server: python start_dev_server.py")
    print("4. View API docs: http://localhost:5051/docs")
    print("\n🔐 Test Credentials:")
    print("   Email: admin@test.com")
    print("   Password: AdminTest123!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
