# Mail Analysis API Configuration Guide

This document provides detailed information on configuring the Mail Analysis API system.

## Configuration File Structure

The Mail Analysis API uses a YAML configuration file for settings. The default location is `config/settings.yaml`.

```yaml
# Example configuration file
app:
  env: "production"
  max_attachment_size: 25MB
  allowed_file_types:
    extensions: [".pdf", ".docx", ".xlsx", ".pptx", ".eml", ".txt"]
    mime_types: 
      - "application/pdf"
      - "application/vnd.openxmlformats-officedocument.*"
      - "text/plain"
      - "message/rfc822"

rate_limits:
  tiers:
    free:
      requests_per_minute: 10
      max_concurrent: 2
    pro:
      requests_per_minute: 100
      max_concurrent: 20
    enterprise:
      requests_per_minute: 1000
      max_concurrent: 100

openai:
  max_tokens_per_request: 4096
  monthly_cost_limit: 1000
  model_choices:
    - "gpt-4-1106-preview"
    - "gpt-3.5-turbo-1106"
  fallback_model: "gpt-3.5-turbo-1106"

notifications:
  email:
    enabled: false
    smtp_server: "smtp.example.com"
    smtp_port: 587
    sender: "noreply@mailanalyzer.com"
    recipients: ["devops@company.com"]
  log_file:
    path: "logs/errors.log"
    max_size: 100MB
    backup_count: 5
```

## Configuration Sections

### App Configuration

| Setting | Type | Description | Default |
|---------|------|-------------|---------|
| env | string | Environment name (development, testing, production) | "development" |
| max_attachment_size | ByteSize | Maximum allowed attachment size | 25MB |
| allowed_file_types.extensions | list | List of allowed file extensions | [".pdf", ".docx", ".xlsx", ".pptx", ".eml", ".txt"] |
| allowed_file_types.mime_types | list | List of allowed MIME types (supports wildcards) | ["application/pdf", "application/vnd.openxmlformats-officedocument.*", "text/plain", "message/rfc822"] |

### Rate Limits Configuration

| Setting | Type | Description | Default |
|---------|------|-------------|---------|
| rate_limits.tiers.free.requests_per_minute | integer | Maximum requests per minute for free tier | 10 |
| rate_limits.tiers.free.max_concurrent | integer | Maximum concurrent requests for free tier | 2 |
| rate_limits.tiers.pro.requests_per_minute | integer | Maximum requests per minute for pro tier | 100 |
| rate_limits.tiers.pro.max_concurrent | integer | Maximum concurrent requests for pro tier | 20 |
| rate_limits.tiers.enterprise.requests_per_minute | integer | Maximum requests per minute for enterprise tier | 1000 |
| rate_limits.tiers.enterprise.max_concurrent | integer | Maximum concurrent requests for enterprise tier | 100 |

### OpenAI Configuration

| Setting | Type | Description | Default |
|---------|------|-------------|---------|
| openai.max_tokens_per_request | integer | Maximum tokens per OpenAI request | 4096 |
| openai.monthly_cost_limit | float | Monthly cost limit in USD | 1000 |
| openai.model_choices | list | List of available OpenAI models | ["gpt-4-1106-preview", "gpt-3.5-turbo-1106"] |
| openai.fallback_model | string | Fallback model if primary is unavailable | "gpt-3.5-turbo-1106" |

### Notifications Configuration

| Setting | Type | Description | Default |
|---------|------|-------------|---------|
| notifications.email.enabled | boolean | Enable email notifications | false |
| notifications.email.smtp_server | string | SMTP server hostname | "smtp.example.com" |
| notifications.email.smtp_port | integer | SMTP server port | 587 |
| notifications.email.sender | string | Sender email address | "noreply@mailanalyzer.com" |
| notifications.email.recipients | list | List of recipient email addresses | ["devops@company.com"] |
| notifications.log_file.path | string | Log file path | "logs/errors.log" |
| notifications.log_file.max_size | ByteSize | Maximum log file size | 100MB |
| notifications.log_file.backup_count | integer | Number of log file backups to keep | 5 |

## Environment Variables

Environment variables can be used to override configuration settings or provide sensitive information that shouldn't be stored in the configuration file.

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| REDIS_HOST | Redis server hostname | localhost | Yes |
| REDIS_PORT | Redis server port | 6379 | No |
| REDIS_PASSWORD | Redis server password | None | No |
| RABBITMQ_HOST | RabbitMQ server hostname | localhost | Yes |
| RABBITMQ_PORT | RabbitMQ server port | 5672 | No |
| RABBITMQ_USER | RabbitMQ username | guest | No |
| RABBITMQ_PASSWORD | RabbitMQ password | guest | No |
| OPENAI_API_KEY | OpenAI API key | None | Yes |
| OPENAI_BACKUP_API_KEYS | Comma-separated list of backup OpenAI API keys | None | No |
| LOG_LEVEL | Application log level | INFO | No |
| CONFIG_PATH | Path to configuration file | config/settings.yaml | No |
| ENCRYPTION_KEY | Key for encrypting sensitive data | None | Yes |

## Configuration Loading

The application loads configuration in the following order, with later sources overriding earlier ones:

1. Default values
2. Configuration file
3. Environment variables

```python
class Config(BaseSettings):
    """Application configuration"""
    
    # Redis configuration
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    
    # RabbitMQ configuration
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    
    # OpenAI configuration
    openai_api_key: str
    openai_backup_api_keys: str = ""
    
    # Logging configuration
    log_level: str = "INFO"
    
    # Configuration file path
    config_path: str = "config/settings.yaml"
    
    # Encryption key
    encryption_key: str
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        
def load_config():
    """Load application configuration"""
    # Load environment variables
    env_config = Config()
    
    # Load configuration file
    config_path = env_config.config_path
    
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            file_config = yaml.safe_load(f)
    else:
        file_config = {}
        
    # Merge configurations
    merged_config = {**file_config}
    
    # Override with environment variables
    for key, value in env_config.dict().items():
        if key in ["redis_host", "redis_port", "redis_password"]:
            merged_config.setdefault("redis", {})[key.replace("redis_", "")] = value
        elif key in ["rabbitmq_host", "rabbitmq_port", "rabbitmq_user", "rabbitmq_password"]:
            merged_config.setdefault("rabbitmq", {})[key.replace("rabbitmq_", "")] = value
        elif key in ["openai_api_key", "openai_backup_api_keys"]:
            merged_config.setdefault("openai", {})[key.replace("openai_", "")] = value
        elif key == "log_level":
            merged_config.setdefault("logging", {})["level"] = value
        elif key == "encryption_key":
            merged_config.setdefault("security", {})["encryption_key"] = value
            
    return merged_config
```

## Configuration Validation

The application validates the configuration at startup to ensure all required settings are present and have valid values.

```python
def validate_config(config: dict) -> bool:
    """
    Validate configuration
    
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
    if not isinstance(app_config.get("max_attachment_size"), (int, float)):
        logger.error("Invalid max_attachment_size: must be a number")
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
```

## Configuration Examples

### Development Environment

```yaml
app:
  env: "development"
  max_attachment_size: 50MB
  allowed_file_types:
    extensions: [".pdf", ".docx", ".xlsx", ".pptx", ".eml", ".txt"]
    mime_types: 
      - "application/pdf"
      - "application/vnd.openxmlformats-officedocument.*"
      - "text/plain"
      - "message/rfc822"

rate_limits:
  tiers:
    free:
      requests_per_minute: 100
      max_concurrent: 10
    pro:
      requests_per_minute: 200
      max_concurrent: 20
    enterprise:
      requests_per_minute: 300
      max_concurrent: 30

openai:
  max_tokens_per_request: 4096
  monthly_cost_limit: 100
  model_choices:
    - "gpt-3.5-turbo-1106"
  fallback_model: "gpt-3.5-turbo-1106"

notifications:
  email:
    enabled: false
  log_file:
    path: "logs/dev-errors.log"
    max_size: 10MB
    backup_count: 2
```

### Production Environment

```yaml
app:
  env: "production"
  max_attachment_size: 25MB
  allowed_file_types:
    extensions: [".pdf", ".docx", ".xlsx", ".pptx", ".eml", ".txt"]
    mime_types: 
      - "application/pdf"
      - "application/vnd.openxmlformats-officedocument.*"
      - "text/plain"
      - "message/rfc822"

rate_limits:
  tiers:
    free:
      requests_per_minute: 10
      max_concurrent: 2
    pro:
      requests_per_minute: 100
      max_concurrent: 20
    enterprise:
      requests_per_minute: 1000
      max_concurrent: 100

openai:
  max_tokens_per_request: 4096
  monthly_cost_limit: 1000
  model_choices:
    - "gpt-4-1106-preview"
    - "gpt-3.5-turbo-1106"
  fallback_model: "gpt-3.5-turbo-1106"

notifications:
  email:
    enabled: true
    smtp_server: "smtp.example.com"
    smtp_port: 587
    sender: "noreply@mailanalyzer.com"
    recipients: ["devops@company.com", "alerts@company.com"]
  log_file:
    path: "/var/log/mail-analysis/errors.log"
    max_size: 100MB
    backup_count: 10
```

## Configuration Management Best Practices

### Environment-Specific Configuration

Use different configuration files for different environments:

```bash
# Development
CONFIG_PATH=config/development.yaml python app.py

# Testing
CONFIG_PATH=config/testing.yaml python app.py

# Production
CONFIG_PATH=config/production.yaml python app.py
```

### Sensitive Information

Store sensitive information in environment variables or a secure vault:

```bash
# .env file (do not commit to version control)
REDIS_PASSWORD=your-redis-password
RABBITMQ_PASSWORD=your-rabbitmq-password
OPENAI_API_KEY=your-openai-api-key
ENCRYPTION_KEY=your-encryption-key
```

### Configuration Versioning

Include a version in your configuration file to track changes:

```yaml
version: "1.0.0"
app:
  env: "production"
  # ...
```

### Configuration Validation

Validate configuration at startup:

```python
@app.on_event("startup")
async def startup_event():
    """Startup event handler"""
    # Load and validate configuration
    config = load_config()
    
    if not validate_config(config):
        logger.critical("Invalid configuration, shutting down")
        sys.exit(1)
        
    # Initialize services with configuration
    # ...
```

### Configuration Reloading

Support configuration reloading without restart:

```python
@app.post("/admin/reload-config")
async def reload_config(
    api_key: str = Header(..., alias="X-API-Key")
):
    """
    Reload configuration
    
    Args:
        api_key: Admin API key
    """
    # Verify admin API key
    key_info = await validate_api_key(api_key)
    
    if "admin" not in key_info["permissions"]:
        raise HTTPException(
            status_code=403,
            detail="Admin permission required"
        )
    
    # Reload configuration
    new_config = load_config()
    
    if not validate_config(new_config):
        return {
            "status": "error",
            "message": "Invalid configuration, not applied"
        }
        
    # Apply new configuration
    global config
    config = new_config
    
    # Update services with new configuration
    # ...
    
    return {
        "status": "success",
        "message": "Configuration reloaded"
    }
```

## Troubleshooting Configuration Issues

### Common Issues

1. **Missing Required Settings**
   - Error: `Missing required configuration section: app`
   - Solution: Ensure all required sections are present in the configuration file

2. **Invalid Setting Values**
   - Error: `Invalid max_attachment_size: must be a number`
   - Solution: Check the type and value of each setting

3. **Environment Variable Precedence**
   - Issue: Configuration file settings not taking effect
   - Solution: Check if environment variables are overriding the settings

4. **File Permissions**
   - Issue: Unable to read configuration file
   - Solution: Ensure the application has read permissions for the configuration file

5. **YAML Syntax Errors**
   - Error: `yaml.YAMLError: mapping values are not allowed here`
   - Solution: Validate YAML syntax with a linter

### Configuration Debugging

Enable debug logging to troubleshoot configuration issues:

```bash
LOG_LEVEL=DEBUG python app.py
```

This will output detailed information about the configuration loading process:

```
DEBUG:config:Loading configuration from config/settings.yaml
DEBUG:config:Overriding redis.host with environment variable REDIS_HOST
DEBUG:config:Overriding redis.port with environment variable REDIS_PORT
DEBUG:config:Overriding openai.api_key with environment variable OPENAI_API_KEY
DEBUG:config:Final configuration: {'app': {'env': 'development', ...}, ...}
```

### Configuration Validation Tool

Use a validation tool to check configuration files:

```python
# validate_config.py
import sys
import yaml
from app.config import validate_config

def main():
    """Validate configuration file"""
    if len(sys.argv) < 2:
        print("Usage: python validate_config.py <config_file>")
        sys.exit(1)
        
    config_file = sys.argv[1]
    
    try:
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading configuration file: {str(e)}")
        sys.exit(1)
        
    if validate_config(config):
        print("Configuration is valid")
        sys.exit(0)
    else:
        print("Configuration is invalid")
        sys.exit(1)
        
if __name__ == "__main__":
    main()
```

Usage:

```bash
python validate_config.py config/settings.yaml
