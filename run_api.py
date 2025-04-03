#!/usr/bin/env python3
"""
Script to run the Mail Analysis API server.
"""

import uvicorn
from app.core.config import config

if __name__ == "__main__":
    """Run the API server."""
    # Get port from config or use default
    port = config.get("app", {}).get("port", 8000)
    
    # Run the application
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=config.get("app", {}).get("env") == "development"
    )
