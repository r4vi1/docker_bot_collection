#!/usr/bin/env python3
"""
banannaBot - Docker Image Mirror Script
Author: Ravi Varma
Version: 2.1
Description: Production-ready script for mirroring Docker images from public repositories 
            to private Quay registries with individual API token support, comprehensive 
            error handling, retries, and banana-themed logging.
            
Features:
- Interactive Docker login for all registries
- Image existence check before push (no overwrite)
- Time-based log rotation with automatic zipping
"""

# Import all required Python libraries
import subprocess  # For running docker and curl commands
import sys         # For system exit codes
import logging     # For creating log files
import json        # For API data formatting
import time        # For timestamps and delays
import os          # For environment variables and file operations
import getpass     # For secure password input
import gzip        # For compressing log files
import shutil      # For file operations
from datetime import datetime, timedelta
from pathlib import Path

# Try to import our configuration file
try:
    from banannaBot_config import (
        REGISTRIES, ALLOWED_SOURCE_REGISTRIES, IMAGES_TO_MIRROR, 
        LOG_CONFIG, OPERATION_CONFIG, validate_config
    )
except ImportError as e:
    print(f"Error importing configuration: {e}")
    print("Please ensure banannaBot_config.py is in the same directory.")
    sys.exit(1)

# ------ LOGGING SETUP WITH BANANA THEME AND TIME-BASED ROTATION ------

class TimeRotatingLogHandler(logging.Handler):
    """
    Custom log handler that rotates logs based on time and zips old log files.
    """
    def __init__(self, log_dir, base_filename, rotation_days):
        super().__init__()
        self.log_dir = Path(log_dir)
        self.base_filename = base_filename
        self.rotation_days = rotation_days
        self.current_log_file = None
        self.file_handler = None
        
        # Create logs directory if it doesn't exist
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize the current log file
        self._rotate_if_needed()
    
    def _get_current_log_path(self):
        """Get the path for the current active log file."""
        return self.log_dir / self.base_filename
    
    def _get_rotation_marker_path(self):
        """Get the path for the rotation marker file (tracks last rotation)."""
        return self.log_dir / ".last_rotation"
    
    def _should_rotate(self):
        """Check if log rotation is needed based on time."""
        marker_file = self._get_rotation_marker_path()
        
        if not marker_file.exists():
            return True
        
        # Read last rotation time
        try:
            with open(marker_file, 'r') as f:
                last_rotation_str = f.read().strip()
                last_rotation = datetime.fromisoformat(last_rotation_str)
                
            # Check if rotation_days have passed
            if datetime.now() - last_rotation >= timedelta(days=self.rotation_days):
                return True
        except Exception:
            return True
        
        return False
    
    def _rotate_if_needed(self):
        """Rotate the log file if needed."""
        current_log = self._get_current_log_path()
        
        if self._should_rotate() and current_log.exists():
            # Archive the current log file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archived_name = f"{current_log.stem}_{timestamp}.log"
            archived_path = self.log_dir / archived_name
            
            # Close the current file handler if it exists
            if self.file_handler:
                self.file_handler.close()
                self.file_handler = None
            
            # Move current log to archived name
            shutil.move(str(current_log), str(archived_path))
            
            # Compress the archived log
            compressed_path = self.log_dir / f"{archived_name}.gz"
            with open(archived_path, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Remove the uncompressed archived log
            archived_path.unlink()
            
            print(f"Log rotated and compressed: {compressed_path}")
            
            # Update rotation marker
            with open(self._get_rotation_marker_path(), 'w') as f:
                f.write(datetime.now().isoformat())
        
        # Create or open the current log file
        if not self.file_handler:
            self.file_handler = logging.FileHandler(current_log, mode='a')
            self.file_handler.setFormatter(self.formatter)
    
    def emit(self, record):
        """Emit a log record."""
        self._rotate_if_needed()
        if self.file_handler:
            self.file_handler.emit(record)
    
    def close(self):
        """Close the handler."""
        if self.file_handler:
            self.file_handler.close()
        super().close()

# Set up enhanced logging with time-based rotation
logger = logging.getLogger('BananaBot')
logger.setLevel(getattr(logging, LOG_CONFIG['level']))

# Clear any existing handlers to avoid duplicate logs
logger.handlers.clear()

# Time-based rotating file handler with compression
file_handler = TimeRotatingLogHandler(
    LOG_CONFIG['log_dir'],
    LOG_CONFIG['file'],
    LOG_CONFIG['rotation_days']
)
file_formatter = logging.Formatter('%(asctime)s 🍌 [%(levelname)s] %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# Console handler for real-time monitoring (if enabled)
if LOG_CONFIG.get('console_output', False):
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter('🍌 [%(levelname)s] %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

def banana_log(step, message, level='info', error_code='SUCCESS'):
    """
    Log messages with banana theme and clear error codes.
    
    Args:
        step: What operation is being performed
        message: The actual message to log
        level: Log level (info, warning, error, debug)
        error_code: Clear error code for troubleshooting
    """
    formatted_message = f"[{error_code}] {step}: {message}"
    
    if level == 'info':
        logger.info(formatted_message)
    elif level == 'warning':
        logger.warning(formatted_message)
    elif level == 'error':
        logger.error(formatted_message)
    elif level == 'debug':
        logger.debug(formatted_message)

# ------ DOCKER LOGIN FUNCTION ------
def docker_login_all_registries():
    """
    Interactively prompt for credentials and login to registries that are actually used.
    
    Returns:
        True if all logins successful, False otherwise
    """
    banana_log("Docker Login", 
              "🍌 Starting authentication to required registries", 
              'info', 'LOGIN_START')
    
    # Determine which environments are actually used
    used_envs = set()
    for image_config in IMAGES_TO_MIRROR.values():
        used_envs.update(image_config.get('targets', []))
    
    if not used_envs:
        banana_log("Docker Login", 
                  "No target environments configured, skipping authentication", 
                  'warning', 'LOGIN_NO_TARGETS')
        return True
    
    print("\n" + "="*70)
    print("DOCKER AUTHENTICATION REQUIRED")
    print("="*70)
    print(f"banannaBot needs to login to registries for: {', '.join(sorted(used_envs))}")
    print("Please provide credentials for each registry.\n")
    
    all_success = True
    unique_registries = set()
    
    # Collect unique registry URLs only for used environments
    for env in used_envs:
        if env in REGISTRIES:
            config = REGISTRIES[env]
            unique_registries.add((config['url'], env))
    
    # Login to each unique registry
    for registry_url, env_name in sorted(unique_registries):
        print(f"\n{'─'*70}")
        print(f"Registry: {registry_url} ({env_name} environment)")
        print(f"{'─'*70}")
        
        # Prompt for username
        username = input(f"Username for {registry_url}: ").strip()
        if not username:
            banana_log("Docker Login", 
                      f"No username provided for {registry_url}", 
                      'error', 'LOGIN_NO_USERNAME')
            all_success = False
            continue
        
        # Prompt for password (hidden input)
        password = getpass.getpass(f"Password for {registry_url}: ")
        if not password:
            banana_log("Docker Login", 
                      f"No password provided for {registry_url}", 
                      'error', 'LOGIN_NO_PASSWORD')
            all_success = False
            continue
        
        # Perform docker login
        try:
            cmd = ["docker", "login", registry_url, "-u", username, "--password-stdin"]
            result = subprocess.run(
                cmd, 
                input=password.encode(), 
                capture_output=True, 
                timeout=30
            )
            
            if result.returncode == 0:
                print(f"Successfully logged in to {registry_url}")
                banana_log("Docker Login", 
                          f"Successfully authenticated to {registry_url}", 
                          'info', 'LOGIN_SUCCESS')
            else:
                error_msg = result.stderr.decode() if result.stderr else "Unknown error"
                print(f"Failed to login to {registry_url}: {error_msg}")
                banana_log("Docker Login", 
                          f"Authentication failed for {registry_url}: {error_msg}", 
                          'error', 'LOGIN_FAILED')
                all_success = False
                
        except subprocess.TimeoutExpired:
            print(f"Login timeout for {registry_url}")
            banana_log("Docker Login", 
                      f"Login timeout for {registry_url}", 
                      'error', 'LOGIN_TIMEOUT')
            all_success = False
        except Exception as e:
            print(f"Unexpected error logging in to {registry_url}: {str(e)}")
            banana_log("Docker Login", 
                      f"Unexpected login error for {registry_url}: {str(e)}", 
                      'error', 'LOGIN_EXCEPTION')
            all_success = False
    
    print("\n" + "="*70)
    if all_success:
        print("All registry authentications successful")
        banana_log("Docker Login", 
                  "All registry authentications completed successfully", 
                  'info', 'LOGIN_ALL_SUCCESS')
    else:
        print("Some registry authentications failed - will attempt to continue")
        banana_log("Docker Login", 
                  "One or more registry authentications failed - continuing anyway", 
                  'warning', 'LOGIN_PARTIAL_FAIL')
    print("="*70 + "\n")
    
    # Always return True to allow script to continue
    # Individual operations will fail if authentication is required
    return True

# ------ IMAGE EXISTENCE CHECK FUNCTION ------
def image_exists_in_registry(image_url):
    """
    Check if an image:tag already exists in the registry using docker manifest inspect.
    
    Args:
        image_url: Full image URL including tag (e.g., registry/namespace/image:tag)
    
    Returns:
        True if image exists, False otherwise
    """
    try:
        cmd = ["docker", "manifest", "inspect", image_url]
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            timeout=30,
            text=True
        )
        
        if result.returncode == 0:
            banana_log("Image Check", 
                      f"Image already exists in registry: {image_url}", 
                      'info', 'IMAGE_EXISTS')
            return True
        else:
            banana_log("Image Check", 
                      f"Image not found in registry: {image_url}", 
                      'debug', 'IMAGE_NOT_EXISTS')
            return False
            
    except subprocess.TimeoutExpired:
        banana_log("Image Check", 
                  f"Timeout checking image existence: {image_url}", 
                  'warning', 'IMAGE_CHECK_TIMEOUT')
        return False
    except Exception as e:
        banana_log("Image Check", 
                  f"Error checking image existence: {image_url} - {str(e)}", 
                  'warning', 'IMAGE_CHECK_ERROR')
        return False

# ------ QUAY REPOSITORY CREATION FUNCTION ------
def create_quay_repo(registry_config, repo_path):
    """
    Create a repository in Quay registry using the API.
    
    Args:
        registry_config: Dictionary with registry URL, namespace, and API token
        repo_path: The repository path to create (e.g., "tsg1-apigee-anthos-prod/image-name")
    
    Returns:
        True if repo was created or already exists, False if failed
    """
    # Build the API URL for repository creation
    api_url = f"https://{registry_config['url']}/api/v1/repository"
    
    # Use the full repository path (e.g., "tsg1-apigee-anthos-prod/account-validation-rajasthan-prod")
    # This preserves the project structure in the Quay repository
    
    # Prepare the data for the API request
    data = {
        "namespace": registry_config['organization'],  # Organization in Quay
        "repository": repo_path,                       # Full repository path including project
        "visibility": "private",                       # Keep it private
        "description": f"🍌 Auto-created by banannaBot on {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "repo_kind": "image"                          # This is an image repository
    }
    
    # Build the curl command with proper authentication
    cmd = [
        "curl", "-s",                                    # Silent mode
        "-w", "%{http_code}",                           # Return HTTP status code
        "--max-time", str(OPERATION_CONFIG['api_timeout']),  # Timeout
        "-X", "POST",                                   # POST request
        "-H", f"Authorization: Bearer {registry_config['api_token']}",  # Auth header
        "-H", "Content-Type: application/json",        # Content type
        "--data", json.dumps(data),                     # JSON payload
        api_url                                         # Target URL
    ]
    
    # Try the API call with retries
    for attempt in range(OPERATION_CONFIG['max_retries']):
        try:
            banana_log("Repository Creation", 
                      f"Attempt {attempt + 1}: Creating repository {repo_path}", 
                      'info', 'REPO_CREATING')
            
            # Run the curl command
            result = subprocess.run(cmd, capture_output=True, text=True, 
                                  timeout=OPERATION_CONFIG['api_timeout'])
            
            # Parse the response - curl returns body + HTTP code
            lines = result.stdout.strip().split('\n')
            http_code = lines[-1] if lines else "000"  # Last line is the HTTP code
            response_body = '\n'.join(lines[:-1]) if len(lines) > 1 else ""
            
            # Handle different HTTP response codes
            if http_code == "201":
                banana_log("Repository Creation", 
                          f"Repository created successfully: {repo_path}", 
                          'info', 'REPO_CREATED')
                return True
                
            elif http_code == "400":
                # Check if it's because repository already exists
                if "already exists" in response_body.lower():
                    banana_log("Repository Creation", 
                              f"Repository already exists: {repo_path}", 
                              'info', 'REPO_EXISTS')
                    return True
                else:
                    banana_log("Repository Creation", 
                              f"Bad request for {repo_path}: {response_body}", 
                              'warning', 'REPO_BAD_REQUEST')
                    
            elif http_code == "401":
                banana_log("Repository Creation", 
                          f"Authentication failed for {repo_path} - check API token", 
                          'error', 'REPO_AUTH_FAILED')
                return False  # Don't retry auth failures
                
            elif http_code == "403":
                banana_log("Repository Creation", 
                          f"Permission denied for {repo_path} - insufficient privileges", 
                          'error', 'REPO_PERMISSION_DENIED')
                return False  # Don't retry permission failures
                
            else:
                banana_log("Repository Creation", 
                          f"Unexpected HTTP code {http_code} for {repo_path}: {response_body}", 
                          'error', f'REPO_HTTP_{http_code}')
            
            # If we get here and it's not the last attempt, wait before retrying
            if attempt < OPERATION_CONFIG['max_retries'] - 1:
                banana_log("Repository Creation", 
                          f"Retrying in {OPERATION_CONFIG['retry_delay']}s", 
                          'info', 'REPO_RETRY')
                time.sleep(OPERATION_CONFIG['retry_delay'])
                
        except subprocess.TimeoutExpired:
            banana_log("Repository Creation", 
                      f"API timeout for {repo_path} (>{OPERATION_CONFIG['api_timeout']}s)", 
                      'error', 'REPO_TIMEOUT')
            if attempt < OPERATION_CONFIG['max_retries'] - 1:
                time.sleep(OPERATION_CONFIG['retry_delay'])
                
        except Exception as e:
            banana_log("Repository Creation", 
                      f"Unexpected error for {repo_path}: {str(e)}", 
                      'error', 'REPO_EXCEPTION')
            if attempt < OPERATION_CONFIG['max_retries'] - 1:
                time.sleep(OPERATION_CONFIG['retry_delay'])
    
    # All retries failed
    banana_log("Repository Creation", 
              f"Repository creation failed for {repo_path} after {OPERATION_CONFIG['max_retries']} attempts", 
              'error', 'REPO_CREATE_FAILED')
    return False

# ------ DOCKER COMMAND EXECUTION FUNCTION ------
def run_docker(*args):
    """
    Run docker commands with proper error handling and retries.
    
    Args:
        *args: Docker command arguments (e.g., "pull", "image:tag")
    
    Returns:
        True if command succeeded, False if failed
    """
    # Build the full docker command
    cmd = ["docker"] + list(args)
    cmd_str = ' '.join(cmd)
    
    # Try the command with retries
    for attempt in range(OPERATION_CONFIG['max_retries']):
        try:
            banana_log("Docker Command", 
                      f"Attempt {attempt + 1}: Running {cmd_str}...", 
                      'info', 'DOCKER_RUNNING')
            
            start_time = time.time()
            
            # Run the docker command with timeout
            subprocess.run(cmd, check=True, capture_output=True, text=True, 
                          timeout=OPERATION_CONFIG['docker_timeout'])
            
            duration = time.time() - start_time
            banana_log("Docker Command", 
                      f"Command successful: {cmd_str} (took {duration:.2f}s)", 
                      'info', 'DOCKER_SUCCESS')
            return True
            
        except subprocess.CalledProcessError as e:
            # Docker command failed - get error details
            error_msg = e.stderr.decode() if hasattr(e.stderr, 'decode') else str(e.stderr)
            if not error_msg:
                error_msg = f"Exit code: {e.returncode}"
                
            banana_log("Docker Command", 
                      f"Command failed: {cmd_str} | Error: {error_msg}", 
                      'error', f'DOCKER_EXIT_{e.returncode}')
            
            # Some errors shouldn't be retried (like image not found)
            if e.returncode in [125, 1] and "not found" in error_msg.lower():
                banana_log("Docker Command", 
                          f"Image not found, skipping retries: {cmd_str}", 
                          'error', 'DOCKER_NOT_FOUND')
                return False
            
            if attempt < OPERATION_CONFIG['max_retries'] - 1:
                banana_log("Docker Command", 
                          f"Retrying in {OPERATION_CONFIG['retry_delay']}s", 
                          'info', 'DOCKER_RETRY')
                time.sleep(OPERATION_CONFIG['retry_delay'])
            else:
                return False
                
        except subprocess.TimeoutExpired:
            banana_log("Docker Command", 
                      f"Command timeout: {cmd_str} (>{OPERATION_CONFIG['docker_timeout']}s)", 
                      'error', 'DOCKER_TIMEOUT')
            if attempt < OPERATION_CONFIG['max_retries'] - 1:
                time.sleep(OPERATION_CONFIG['retry_delay'])
            else:
                return False
                
        except Exception as e:
            banana_log("Docker Command", 
                      f"Unexpected error: {cmd_str} | {str(e)}", 
                      'error', 'DOCKER_EXCEPTION')
            if attempt < OPERATION_CONFIG['max_retries'] - 1:
                time.sleep(OPERATION_CONFIG['retry_delay'])
            else:
                return False
    
    return False

# ------ IMAGE PATH CONSTRUCTION FUNCTION ------
def get_destination_image_path(source_img, registry_config):
    """
    Parse source image URL and construct destination paths for Quay registry.
    
    This function implements the specific logic for your registry structure:
    # Source: region-docker.pkg.dev/project-id/repo-name/image:tag
    # Dest:   quay-registry.example.com/namespace/project-id/image:tag
    
    Args:
        source_img: The source image URL
        registry_config: Target registry configuration
    
    Returns:
        tuple: (dest_img, latest_img, repo_path, tag)
    """
    # Split the source image URL into parts
    # Example: ["asia-south1-docker.pkg.dev", "tsg1-apigee-anthos-prod", "asia-south1-docker-pkg-dev", "account-validation-rajasthan-prod:f7b4af8"]
    parts = source_img.split('/')
    
    # Extract the project (always the second part)
    project = parts[1]  # "tsg1-apigee-anthos-prod"
    
    # Extract image name and tag from the last part
    image_name_with_tag = parts[-1]  # "account-validation-rajasthan-prod:f7b4af8"
    image_name, tag = image_name_with_tag.split(':')  # "account-validation-rajasthan-prod", "f7b4af8"
    
    # Get registry details
    quay_url = registry_config['url']
    org = registry_config['namespace']
    
    # Construct destination image paths
    dest_img = f"{quay_url}/{org}/{project}/{image_name}:{tag}"      # Original tag
    latest_img = f"{quay_url}/{org}/{project}/{image_name}:latest"   # Latest tag
    repo_path = f"{project}/{image_name}"                            # For API calls
    
    banana_log("Path Construction", 
              f"Source: {source_img} → Dest: {dest_img}", 
              'debug', 'PATH_MAPPED')
    
    return dest_img, latest_img, repo_path, tag

# ------ MAIN IMAGE MIRRORING FUNCTION ------
def mirror_image(source_img, target_envs, description=""):
    """
    Mirror a single image to specified target environments.
    This is the core function that orchestrates all the mirroring steps.
    
    Args:
        source_img: The source image URL to mirror
        target_envs: List of target environments ["prod", "dr", "uat"]
        description: Optional description for logging
    
    Returns:
        True if mirroring was successful for all targets, False otherwise
    """
    banana_log("Image Mirroring", 
              f"🍌 Starting mirror for: {source_img}", 
              'info', 'MIRROR_START')
    
    if description:
        banana_log("Image Description", f"Mission details: {description}", 'info', 'MIRROR_DESC')
    
    overall_success = True
    
    # Step 1: Validate that the source image is from an allowed registry
    source_prefix = "/".join(source_img.split('/')[:2])  # e.g., "asia-south1-docker.pkg.dev/tsg1-apigee-anthos-prod"
    
    if source_prefix not in ALLOWED_SOURCE_REGISTRIES:
        banana_log("Source Validation", 
                  f"Source registry not authorized: {source_prefix}", 
                  'error', 'SOURCE_UNAUTHORIZED')
        return False
    
    banana_log("Source Validation", 
              f"Source registry validated: {source_prefix}", 
              'info', 'SOURCE_AUTHORIZED')
    
    # Step 2: Pull the source image from public registry
    if not run_docker("pull", source_img):
        banana_log("Image Pull", 
                  f"Failed to pull image from source: {source_img}", 
                  'error', 'PULL_FAILED')
        if not OPERATION_CONFIG['continue_on_error']:
            return False
        overall_success = False
    
    # Step 3: Process each target environment
    for env in target_envs:
        # Validate environment exists in configuration
        if env not in REGISTRIES:
            banana_log("Environment Validation", 
                      f"Unknown target environment: {env}", 
                      'error', 'ENV_UNKNOWN')
            overall_success = False
            continue
        
        banana_log("Environment Processing", 
                  f"Processing environment: {env}", 
                  'info', 'ENV_PROCESSING')
        
        registry_config = REGISTRIES[env]
        
        # Get destination image paths using our custom logic
        dest_img, latest_img, repo_path, tag = get_destination_image_path(source_img, registry_config)
        
        # Step 4: Check if image:tag already exists in registry
        if image_exists_in_registry(dest_img):
            banana_log("Image Existence", 
                      f"Image {tag} already exists in {env}, skipping: {dest_img}", 
                      'info', 'IMAGE_ALREADY_EXISTS')
            print(f"Image {dest_img} already exists - skipping")
            continue  # Skip to next environment
        
        # Step 5: Tag the source image for the destination registry (original tag)
        # We tag first to prepare the image for the specific destination
        if not run_docker("tag", source_img, dest_img):
            banana_log("Image Tagging", 
                      f"Failed to tag image: {dest_img}", 
                      'error', 'TAG_FAILED')
            if not OPERATION_CONFIG['continue_on_error']:
                overall_success = False
                continue
            overall_success = False
            continue
        
        # Step 6: Create repository if it doesn't exist (using Quay API)
        # We create the repo after tagging, based on the tagged image path
        if OPERATION_CONFIG['create_repos_if_not_exists']:
            if not create_quay_repo(registry_config, repo_path):
                banana_log("Repository Check", 
                          f"Failed to create repository for {env}: {repo_path}", 
                          'warning', 'REPO_PREP_FAILED')
                if not OPERATION_CONFIG['continue_on_error']:
                    overall_success = False
                    continue
        
        # Step 7: Push the original tagged image (only if it doesn't exist)
        if not run_docker("push", dest_img):
            banana_log("Image Push", 
                      f"Failed to push image to {env}: {dest_img}", 
                      'error', 'PUSH_FAILED')
            if not OPERATION_CONFIG['continue_on_error']:
                overall_success = False
                continue
            overall_success = False
        else:
            # Only update latest tag if the original tag push was successful
            banana_log("Image Push", 
                      f"Successfully pushed {tag} to {env}", 
                      'info', 'PUSH_SUCCESS')
            
            # Step 8: Tag the source image as "latest" for the destination registry
            if not run_docker("tag", source_img, latest_img):
                banana_log("Latest Tagging", 
                          f"Failed to tag as latest: {latest_img}", 
                          'error', 'LATEST_TAG_FAILED')
                if not OPERATION_CONFIG['continue_on_error']:
                    overall_success = False
                    continue
                overall_success = False
            else:
                # Step 9: Push the "latest" tagged image (overwrite previous latest)
                if not run_docker("push", latest_img):
                    banana_log("Latest Push", 
                              f"Failed to push latest tag to {env}: {latest_img}", 
                              'error', 'LATEST_PUSH_FAILED')
                    if not OPERATION_CONFIG['continue_on_error']:
                        overall_success = False
                        continue
                    overall_success = False
                else:
                    banana_log("Latest Update", 
                              f"Latest tag updated in {env} pointing to {tag}", 
                              'info', 'LATEST_UPDATED')
        
        banana_log("Environment Complete", 
                  f"Successfully mirrored to {env}: {tag} and latest", 
                  'info', 'ENV_SUCCESS')
    
    # Step 10: Cleanup local images if configured
    if OPERATION_CONFIG.get('cleanup_local_images', False):
        banana_log("Cleanup", "Cleaning up local images", 'info', 'CLEANUP_START')
        
        # Remove source image
        run_docker("rmi", source_img)
        
        # Remove all tagged images
        for env in target_envs:
            if env in REGISTRIES:
                registry_config = REGISTRIES[env]
                dest_img, latest_img, _, _ = get_destination_image_path(source_img, registry_config)
                run_docker("rmi", dest_img)
                run_docker("rmi", latest_img)
        
        banana_log("Cleanup", "Local image cleanup complete", 'info', 'CLEANUP_DONE')
    
    # Final status for this image
    if overall_success:
        banana_log("Image Complete", 
                  f"Mirror completed successfully: {source_img} to {target_envs}", 
                  'info', 'MIRROR_SUCCESS')
    else:
        banana_log("Image Complete", 
                  f"Mirror completed with errors: {source_img} (check logs for details)", 
                  'warning', 'MIRROR_PARTIAL')
    
    return overall_success

# ------ MAIN SCRIPT EXECUTION ------
def main():
    """
    Main function that orchestrates the entire mirroring process.
    This is where everything starts when you run the script.
    """
    start_time = time.time()
    
    banana_log("banannaBot Startup", 
              "🍌 banannaBot 2.1 starting up", 
              'info', 'STARTUP')
    
    # Step 1: Validate configuration before starting
    banana_log("Configuration Check", 
              "🍌 Validating configuration", 
              'info', 'CONFIG_CHECKING')
    
    config_issues = validate_config()
    if config_issues:
        banana_log("Configuration Check", 
                  f"Configuration validation failed: {config_issues}", 
                  'error', 'CONFIG_INVALID')
        print("Configuration issues found:")
        for issue in config_issues:
            print(f"  - {issue}")
        print("\nPlease fix these issues before running the script.")
        return 1
    
    banana_log("Configuration Check", 
              "Configuration validated successfully", 
              'info', 'CONFIG_VALID')
    
    # Step 2: Docker login to required registries
    docker_login_all_registries()  # Continue regardless of login success
    
    # Step 3: Initialize tracking variables
    total_images = len(IMAGES_TO_MIRROR)
    successful_images = 0
    failed_images = 0
    
    banana_log("Mirror Planning", 
              f"🍌 Planning to mirror {total_images} images", 
              'info', 'MISSION_PLANNED')
    
    # Step 4: Process each image in the configuration
    for image_counter, (source_img, config) in enumerate(IMAGES_TO_MIRROR.items(), 1):
        target_envs = config.get('targets', [])
        description = config.get('description', 'No description provided')
        
        banana_log("Image Queue", 
                  f"[{image_counter}/{total_images}] Processing: {description}", 
                  'info', 'IMAGE_QUEUED')
        
        banana_log("Image Details", 
                  f"Source: {source_img} | Destinations: {target_envs}", 
                  'info', 'IMAGE_DETAILS')
        
        try:
            # Mirror this specific image
            success = mirror_image(source_img, target_envs, description)
            
            if success:
                successful_images += 1
                banana_log("Image Result", 
                          f"[{image_counter}/{total_images}] Image mirrored successfully", 
                          'info', 'IMAGE_SUCCESS')
            else:
                failed_images += 1
                banana_log("Image Result", 
                          f"[{image_counter}/{total_images}] Image mirror failed", 
                          'warning', 'IMAGE_FAILED')
                
                # Exit immediately if continue_on_error is False
                if not OPERATION_CONFIG['continue_on_error']:
                    banana_log("Mirror Abort", 
                              "Mirror aborted due to error (continue_on_error=False)", 
                              'error', 'MISSION_ABORTED')
                    break
                    
        except Exception as e:
            failed_images += 1
            banana_log("Image Exception", 
                      f"[{image_counter}/{total_images}] Unexpected error: {str(e)}", 
                      'error', 'IMAGE_EXCEPTION')
            
            if not OPERATION_CONFIG['continue_on_error']:
                banana_log("Mirror Abort", 
                          "Mirror aborted due to unexpected error", 
                          'error', 'MISSION_EXCEPTION')
                break
    
    # Step 5: Calculate and report final statistics
    duration = time.time() - start_time
    success_rate = (successful_images / total_images * 100) if total_images > 0 else 0
    
    banana_log("Final Statistics", 
              "🍌 MIRROR OPERATION COMPLETE", 
              'info', 'STATS_HEADER')
    banana_log("Final Statistics", 
              f"Total duration: {duration:.2f} seconds", 
              'info', 'STATS_DURATION')
    banana_log("Final Statistics", 
              f"Images processed: {total_images}", 
              'info', 'STATS_TOTAL')
    banana_log("Final Statistics", 
              f"Successful: {successful_images}", 
              'info', 'STATS_SUCCESS')
    banana_log("Final Statistics", 
              f"Failed: {failed_images}", 
              'info', 'STATS_FAILED')
    banana_log("Final Statistics", 
              f"Success rate: {success_rate:.1f}%", 
              'info', 'STATS_RATE')
    
    # Step 6: Final mirror status
    if successful_images == total_images:
        banana_log("Mirror Complete", 
                  f"All {total_images} images mirrored successfully", 
                  'info', 'MISSION_SUCCESS')
        return 0  # Success exit code
    else:
        banana_log("Mirror Complete", 
                  f"Mirror completed with errors: {successful_images}/{total_images} successful", 
                  'warning', 'MISSION_PARTIAL')
        return 1  # Partial failure exit code

# ------ SCRIPT ENTRY POINT ------
# This is where the script starts when you run "python3 banannaBot.py"
if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        banana_log("User Interrupt", 
                  "banannaBot received stop signal from user - shutting down gracefully", 
                  'info', 'USER_STOP')
        sys.exit(130)  # Standard exit code for Ctrl+C
    except Exception as e:
        banana_log("Fatal Error", 
                  f"banannaBot encountered fatal error: {str(e)}", 
                  'error', 'FATAL_ERROR')
        sys.exit(1)
