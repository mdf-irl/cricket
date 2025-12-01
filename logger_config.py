"""Centralized logging configuration for the D&D bot."""

import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name.
    
    Usage in cogs:
        from logger_config import get_logger
        logger = get_logger(__name__)
    """
    return logging.getLogger(name)
