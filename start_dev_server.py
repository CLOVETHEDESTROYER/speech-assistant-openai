#!/usr/bin/env python3
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
    print("📱 Server will be available at: http://localhost:5051")
    print("📚 API docs will be available at: http://localhost:5051/docs")
    print("🛑 Press Ctrl+C to stop the server")

    try:
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=5051,
            reload=True,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
