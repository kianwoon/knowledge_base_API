#!/usr/bin/env python3
"""
Configuration module for the Mail Analysis API.
"""

import os
import sys
from typing import Dict, Any, Optional, List
import yaml
import pytz
from datetime import datetime, timezone
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings
from loguru import logger


class Settings(BaseSettings):
    """Application settings from environment variables."""
    
    # Redis configuration
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    
    
    # Logging configuration
    log_level: str = "INFO"
    
    # Configuration file path
    config_path: str = "config/settings.yaml"
    
    # Encryption key
    encryption_key: str
    
    # Timezone configuration
    timezone: str = "Asia/Singapore"
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }


def load_yaml_config(file_path: str) -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    
    Args:
        file_path: Path to YAML configuration file
        
    Returns:
        Configuration dictionary
    """
    if not os.path.exists(file_path):
        logger.warning(f"Configuration file not found: {file_path}")
        return {}
        
    try:
        with open(file_path, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Error loading configuration file: {str(e)}")
        return {}


def validate_config(config: Dict[str, Any]) -> bool:
    """
    Validate configuration.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        True if configuration is valid, False otherwise
    """
    # Check required sections
    required_sections = ["app", "rate_limits", "openai"]
    for section in required_sections:
        if section not in config:
            logger.error(f"Missing required configuration section: {section}")
            return False
            
    # Check app configuration
    app_config = config.get("app", {})
    if not isinstance(app_config.get("max_attachment_size"), (int, float, str)):
        logger.error("Invalid max_attachment_size: must be a number or string with unit")
        return False
        
    # Check rate limits configuration
    rate_limits_config = config.get("rate_limits", {}).get("tiers", {})
    for tier in ["free", "pro", "enterprise"]:
        if tier not in rate_limits_config:
            logger.error(f"Missing rate limit configuration for tier: {tier}")
            return False
            
        tier_config = rate_limits_config[tier]
        if not isinstance(tier_config.get("requests_per_minute"), int):
            logger.error(f"Invalid requests_per_minute for tier {tier}: must be an integer")
            return False
            
        if not isinstance(tier_config.get("max_concurrent"), int):
            logger.error(f"Invalid max_concurrent for tier {tier}: must be an integer")
            return False
            
    # Check OpenAI configuration
    openai_config = config.get("openai", {})
    if not isinstance(openai_config.get("max_tokens_per_request"), int):
        logger.error("Invalid max_tokens_per_request: must be an integer")
        return False
        
    if not isinstance(openai_config.get("monthly_cost_limit"), (int, float)):
        logger.error("Invalid monthly_cost_limit: must be a number")
        return False
        
    if not isinstance(openai_config.get("model_choices"), list) or not openai_config.get("model_choices"):
        logger.error("Invalid model_choices: must be a non-empty list")
        return False
        
    if not isinstance(openai_config.get("fallback_model"), str):
        logger.error("Invalid fallback_model: must be a string")
        return False
        
    return True


def merge_configs(env_config: Settings, file_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge environment and file configurations.
    
    Args:
        env_config: Environment configuration
        file_config: File configuration
        
    Returns:
        Merged configuration
    """
    # Start with file configuration
    merged_config = {**file_config}
    
    # Override with environment variables
    for key, value in env_config.model_dump().items():
        if key in ["redis_host", "redis_port", "redis_password"]:
            merged_config.setdefault("redis", {})[key.replace("redis_", "")] = value
        elif key in ["openai_api_key", "openai_backup_api_keys"]:
            merged_config.setdefault("openai", {})[key.replace("openai_", "")] = value
        elif key == "log_level":
            merged_config.setdefault("logging", {})["level"] = value
        elif key == "encryption_key":
            merged_config.setdefault("security", {})["encryption_key"] = value
        elif key == "timezone":
            merged_config.setdefault("app", {})["timezone"] = value
            
    # Handle PORT environment variable separately
    if "PORT" in os.environ:
        try:
            port_value = int(os.environ["PORT"])
            merged_config.setdefault("app", {})["port"] = port_value
        except (ValueError, TypeError):
            logger.warning(f"Invalid PORT environment variable value: {os.environ['PORT']}")
            
    return merged_config


def setup_logging(config: Dict[str, Any]) -> None:
    """
    Set up logging configuration.
    
    Args:
        config: Configuration dictionary
    """
    log_level = config.get("logging", {}).get("level", "INFO")
    
    # Remove default logger
    logger.remove()
    
    # # Add console logger
    # logger.add(
    #     sys.stderr,
    #     level=log_level,
    #     format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    # )


    # Configure Loguru to display job_id and trace_id in logs 
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <yellow>job_id={extra[job_id]}</yellow> | <yellow>trace_id={extra[trace_id]}</yellow> | <level>{message}</level>",
        filter=lambda record: "job_id" in record["extra"] and "trace_id" in record["extra"],
        level="INFO"
    )
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <yellow>trace_id={extra[trace_id]}</yellow> | <level>{message}</level>",
        filter=lambda record: "trace_id" in record["extra"] and "job_id" not in record["extra"],
        level="INFO"
    )
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
        filter=lambda record: "trace_id" not in record["extra"],
        level="INFO"
    )
    
    # Add file logger if configured
    log_file = config.get("notifications", {}).get("log_file", {})
    if log_file.get("path"):
        logger.add(
            log_file.get("path"),
            level=log_level,
            rotation=log_file.get("max_size", "100MB"),
            retention=log_file.get("backup_count", 5),
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"
        )


def load_config() -> Dict[str, Any]:
    """
    Load application configuration.
    
    Returns:
        Configuration dictionary
    """
    # Load environment variables
    try:
        env_config = Settings()
    except Exception as e:
        logger.error(f"Error loading environment variables: {str(e)}")
        sys.exit(1)
    
    # Load configuration file
    file_config = load_yaml_config(env_config.config_path)
    
    # Merge configurations
    config = merge_configs(env_config, file_config)
    
    # Validate configuration
    if not validate_config(config):
        logger.error("Invalid configuration")
        sys.exit(1)
    
    # Set up logging
    setup_logging(config)
    
    # Set default timezone
    timezone_name = config.get("app", {}).get("timezone", "Asia/Singapore")
    try:
        # Set the default timezone for the application
        pytz.timezone(timezone_name)
        logger.info(f"Default timezone set to {timezone_name}")
    except pytz.exceptions.UnknownTimeZoneError:
        logger.error(f"Unknown timezone: {timezone_name}, using UTC instead")
        timezone_name = "UTC"
    
    # Store the timezone in the config
    config.setdefault("app", {})["timezone"] = timezone_name
    
    logger.info(f"Configuration loaded from {env_config.config_path}")
    
    return config


# Global configuration instance
config = load_config()

# Get the configured timezone
def get_timezone():
    """Get the configured timezone."""
    timezone_name = config.get("app", {}).get("timezone", "Asia/Singapore")
    return pytz.timezone(timezone_name)

# Function to get current datetime with timezone
def get_current_datetime():
    """Get current datetime with the configured timezone."""
    tz = get_timezone()
    return datetime.now(tz)

# Function to localize a datetime object to the configured timezone
def localize_datetime(dt):
    """Localize a datetime object to the configured timezone."""
    if dt.tzinfo is None:
        tz = get_timezone()
        return tz.localize(dt)
    return dt
