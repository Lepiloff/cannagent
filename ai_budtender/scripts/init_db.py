#!/usr/bin/env python3
"""
Database initialization script using Alembic migrations
"""

import os
import sys
import subprocess
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.config import settings
from app.core.logging import setup_logging, get_logger

# Setup logging
setup_logging()
logger = get_logger(__name__)


def run_alembic_command(command: str):
    """Run an Alembic command."""
    try:
        result = subprocess.run(
            f"alembic {command}",
            shell=True,
            cwd=project_root,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            logger.info(f"Alembic command successful: {command}")
            if result.stdout:
                print(result.stdout)
        else:
            logger.error(f"Alembic command failed: {command}")
            if result.stderr:
                print(result.stderr)
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Failed to run Alembic command: {e}")
        sys.exit(1)


def init_database():
    """Initialize database with Alembic migrations."""
    logger.info("Initializing database...")
    
    # Create initial migration if it doesn't exist
    if not os.path.exists(project_root / "alembic" / "versions"):
        logger.info("Creating initial migration...")
        run_alembic_command("revision --autogenerate -m 'Initial migration'")
    
    # Apply migrations
    logger.info("Applying database migrations...")
    run_alembic_command("upgrade head")
    
    logger.info("Database initialization completed!")


if __name__ == "__main__":
    init_database() 