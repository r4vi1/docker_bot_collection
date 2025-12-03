# banannaBot - Docker Image Mirror Script

## Overview
banannaBot is a production-ready Python script for mirroring Docker images from public repositories to private Quay registries with comprehensive error handling, retry logic, and time-based log rotation.

## Version
**2.1**

## Author
Ravi Varma

## Files
- `banannaBot.py` - Main script
- `banannaBot_config.py` - Configuration file

## Features

### Core Functionality
1. **Interactive Docker Authentication**
   - Prompts for credentials at startup
   - Secure password input (hidden)
   - Automatic login to all configured registries
   - No manual docker login required

2. **Smart Image Management**
   - Checks if image:tag exists before push
   - Never overwrites existing image tags
   - Only pushes new images
   - Automatically updates "latest" tag when new images are pushed

3. **Time-Based Log Rotation**
   - Logs stored in `logs/` directory
   - Automatic rotation every N days (default: 7 days)
   - Old logs compressed to `.gz` format
   - Timestamped archives for easy reference

4. **Production-Ready Operations**
   - Comprehensive error handling
   - Automatic retries with configurable delays
   - Quay API integration for repository creation
   - Source registry validation
   - Detailed logging with clear error codes

## Configuration

### Registry Setup
Edit `banannaBot_config.py`:

```python
REGISTRIES = {
    "prod": {
        "url": "quay-registry.apps.ocpcorpprod.icicibankltd.com",
        "namespace": "apigee_hybrid_dmz_prod",
        "api_token": "YOUR_TOKEN_HERE",
        "organization": "apigee_hybrid_dmz_prod"
    },
    # Add more environments as needed
}
```

### Log Configuration
```python
LOG_CONFIG = {
    "level": "INFO",  # DEBUG, INFO, WARNING, ERROR
    "file": "banannaBot.log",
    "log_dir": "logs",
    "rotation_days": 7,  # Change to adjust rotation frequency
    "console_output": True
}
```

### Operation Settings
```python
OPERATION_CONFIG = {
    "continue_on_error": True,
    "create_repos_if_not_exists": True,
    "cleanup_local_images": False,
    "docker_timeout": 300,
    "api_timeout": 30,
    "max_retries": 3,
    "retry_delay": 5
}
```

### Images to Mirror
```python
IMAGES_TO_MIRROR = {
    "source/registry/image:tag": {
        "targets": ["prod", "dr"],
        "description": "Description of the image"
    },
    # Add more images as needed
}
```

## Usage

### Run the Script
```bash
python3 banannaBot.py
```

### Validate Configuration
```bash
python3 banannaBot_config.py
```

## Workflow

When you run banannaBot:

1. **Configuration Validation** - Checks config for issues
2. **Docker Authentication** - Prompts for registry credentials
3. **Image Processing** - For each configured image:
   - Pulls from source registry
   - Checks if tag exists in destination
   - If new: pushes image and updates "latest" tag
   - If exists: skips and moves to next
4. **Logging** - All operations logged to `logs/banannaBot.log`
5. **Statistics** - Final report with success/failure counts

## Log Files

### Structure
```
/Users/ravivarma/Documents/
├── banannaBot.py
├── banannaBot_config.py
└── logs/
    ├── banannaBot.log                    # Current log
    ├── .last_rotation                     # Rotation marker (hidden)
    ├── banannaBot_20251001_054630.log.gz  # Archived logs
    └── banannaBot_20251008_102345.log.gz  # Archived logs
```

### Log Format
```
2025-10-04 04:30:15 [INFO] [SUCCESS] banannaBot Startup: banannaBot 2.1 starting up
2025-10-04 04:30:16 [INFO] [CONFIG_VALID] Configuration Check: Configuration validated successfully
2025-10-04 04:30:45 [INFO] [LOGIN_SUCCESS] Docker Login: Successfully authenticated to registry.example.com
```

### Error Codes
- `SUCCESS` - Operation completed successfully
- `LOGIN_*` - Authentication related
- `IMAGE_*` - Image operations (pull, push, tag)
- `REPO_*` - Repository operations
- `DOCKER_*` - Docker command execution
- `CONFIG_*` - Configuration validation
- `MIRROR_*` - Overall mirror operation status

## Troubleshooting

### Check Configuration
```bash
python3 banannaBot_config.py
```

### View Logs
```bash
tail -f logs/banannaBot.log
```

### Debug Mode
Edit `banannaBot_config.py`:
```python
LOG_CONFIG = {
    "level": "DEBUG",  # More verbose logging
    ...
}
```

### Common Issues

**Authentication Failures**
- Check API tokens in config
- Verify registry URLs are correct
- Ensure credentials are valid

**Image Already Exists**
- This is normal - banannaBot protects existing images
- Only new images will be pushed
- Check logs for "IMAGE_ALREADY_EXISTS" code

**Repository Creation Failed**
- Verify API token has required permissions
- Check organization/namespace names
- Review HTTP error codes in logs

## Benefits

1. **Data Safety** - Never overwrites existing image tags
2. **Automation** - No manual docker login required
3. **Reliability** - Automatic retries and error handling
4. **Audit Trail** - Comprehensive logging with rotation
5. **Space Efficient** - Gzip compression saves ~90% disk space
6. **Configurable** - Easy to adjust all parameters

## Security Notes

- Passwords entered interactively (hidden from display)
- API tokens should be stored securely
- Consider using environment variables for tokens
- Log files may contain sensitive registry URLs

## Version History

- **2.1** - Renamed to banannaBot, improved logging clarity
- **2.0** - Added docker login, image existence check, log rotation
- **1.0** - Initial release

## Support

For issues or questions:
1. Check logs in `logs/banannaBot.log`
2. Run configuration validation
3. Review error codes in log messages
4. Check registry connectivity and credentials
