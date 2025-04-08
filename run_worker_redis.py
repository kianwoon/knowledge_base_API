#!/usr/bin/env python3
"""
Script to run the Mail Analysis API worker.
"""

import asyncio
import signal
import sys
from loguru import logger
from app.worker.worker_redis import main

def handle_sigterm(signum, frame):
    """Handle SIGTERM signal."""
    logger.info("SIGTERM received, initiating graceful shutdown...")
    sys.exit(0)

if __name__ == "__main__":
    """Run the worker."""
    # Register signal handlers
    signal.signal(signal.SIGTERM, handle_sigterm)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received in run_worker.py, exiting gracefully...")
    except Exception as e:
        logger.error(f"Unhandled exception in run_worker.py: {str(e)}")
        sys.exit(1)
