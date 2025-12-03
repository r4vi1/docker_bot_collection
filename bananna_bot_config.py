#!/usr/bin/env python3
"""
banannaBot - Configuration File
Author: Ravi Varma
Version: 2.1
Description: Production-ready configuration for mirroring Docker images from public repositories 
            to private Quay registries across Prod, DR, and UAT environments with individual API tokens.
"""

import os

# Registry Configuration with individual API tokens for each environment
# Each registry has its own API token for proper authentication and security
REGISTRIES = {
    "prod": {
        "url": "quay-registry.apps.ocpcorpprod.icicibankltd.com",
        "namespace": "apigee_hybrid_dmz_prod",
        "api_token": "PROD_TOKEN",
        "organization": "apigee_hybrid_dmz_prod"  # Used for API calls
    },
    "dr": {
        "url": "quay-registry.apps.ocpcorpdr.icicibankltd.com", 
        "namespace": "apigee_hybrid_dmz_prod",
        "api_token": "PROD_TOKEN",
        "organization": "apigee_hybrid_dmz_prod"  # Used for API calls
    },
    "uat": {
        "url": "quay-registry.apps.ocpcorpuat.icicibankltd.com",
        "namespace": "tsg1-apigee-hybrid-dmz",
        "api_token": os.getenv("QUAY_UAT_API_TOKEN", "YOUR_UAT_API_TOKEN_HERE"),
        "organization": "tsg1-apigee-hybrid-dmz"  # Used for API calls
    }
}

# Security measure: Only allow images from these two specific registries
# This prevents accidental mirroring of unauthorized images
ALLOWED_SOURCE_REGISTRIES = [
    "asia-south1-docker.pkg.dev/tsg1-apigee-anthos-prod",
    "asia.gcr.io/tsg1-apigee-anthos-prod"
]

# Images to mirror configuration
# Format: "source_image": {
#     "targets": ["prod", "dr", "uat"],  # Which environments to mirror to
#     "description": "Optional description for tracking and logging"
# }
IMAGES_TO_MIRROR = {
    "asia-south1-docker.pkg.dev/tsg1-apigee-anthos-prod/asia-south1-docker-pkg-dev/account-validation-rajasthan-prod:f7b4af8": {
        "targets": ["prod", "dr"],
        "description": "Account validation service for Rajasthan production"
    },
    "asia.gcr.io/tsg1-apigee-anthos-prod/aadhar-seeding-npci-prod:5389f2a": {
        "targets": ["prod", "dr"],
        "description": "Aadhar seeding service for NPCI production"
    },
    # Add more images here as needed
}

# Logging Configuration - Controls how the banana-themed logs are written
LOG_CONFIG = {
    "level": "INFO",  # DEBUG, INFO, WARNING, ERROR
    "file": "image_mirror.log",  # Log file name
    "log_dir": "logs",  # Directory where logs are stored
    "rotation_days": 7,  # Rotate and zip logs every N days (1 week by default)
    "console_output": True  # Also print logs to console (useful for monitoring)
}

# Operation Settings - Fine-tune the behavior of the mirroring process
OPERATION_CONFIG = {
    "continue_on_error": True,  # Set to False to stop on first error
    "create_repos_if_not_exists": True,  # Auto-create repos via Quay API
    "cleanup_local_images": False,  # Set to True to remove local images after mirroring
    "docker_timeout": 300,  # Docker command timeout in seconds (5 minutes)
    "api_timeout": 30,  # API request timeout in seconds
    "max_retries": 3,  # Number of retries for failed operations
    "retry_delay": 5  # Delay between retries in seconds
}

# Function to validate configuration before running the script
def validate_config():
    """
    Validates the configuration to ensure all required settings are present.
    Returns a list of issues found, empty list means configuration is valid.
    """
    issues = []
    
    # Check that API tokens are set for each environment
    for env, config in REGISTRIES.items():
        if config["api_token"] in [None, "", f"YOUR_{env.upper()}_API_TOKEN_HERE"]:
            issues.append(f"Missing or placeholder API token for {env} environment")
    
    # Check that at least one image is configured
    if not IMAGES_TO_MIRROR:
        issues.append("No images configured for mirroring")
    
    # Validate each image configuration
    for image, config in IMAGES_TO_MIRROR.items():
        if not config.get("targets"):
            issues.append(f"No targets specified for image: {image}")
        
        # Ensure the source registry is allowed
        source_prefix = "/".join(image.split("/")[:2])
        if source_prefix not in ALLOWED_SOURCE_REGISTRIES:
            issues.append(f"Image {image} not from allowed source registry")
    
    return issues

# Test the configuration when this file is run directly
if __name__ == "__main__":
    print("banannaBot configuration validation:")
    issues = validate_config()
    if issues:
        print("Issues found:")
        for issue in issues:
            print(f"  - {issue}")
        print("\nPlease fix these issues before running banannaBot.")
    else:
        print("Configuration validated successfully")
        print("Ready to run: python3 banannaBot.py")
