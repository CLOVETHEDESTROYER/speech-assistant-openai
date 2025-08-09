#!/usr/bin/env python3
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
