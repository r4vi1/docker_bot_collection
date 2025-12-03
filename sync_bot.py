#!/usr/bin/env python3
"""
syncBot - Registry Sync Script
Author: Ravi Varma
Version: 1.0
Description: Production-ready script to sync all images from Prod registry to DR registry.
            Lists all repositories and tags from Prod using Quay API, then pulls, tags, 
            pushes, verifies, and cleans up each image systematically.

Features:
- Quay API integration for comprehensive repository listing
- Interactive Docker authentication
- Image existence verification before push
- Post-push verification before local cleanup
- Comprehensive error handling with retries
- Time-based log rotation
- Progress tracking for large-scale operations (270+ repos)
"""

# Import all required Python libraries
import subprocess
import sys
import logging
import json
import time
import os
import getpass
import gzip
import shutil
from datetime import datetime, timedelta
from pathlib import Path

# Try to import configuration from banannaBot
try:
    from banannaBot_config import (
        REGISTRIES, LOG_CONFIG, OPERATION_CONFIG
    )
except ImportError as e:
    print(f"Error importing configuration: {e}")
    print("Please ensure banannaBot_config.py is in the same directory.")
    sys.exit(1)

# ------ LOGGING SETUP WITH TIME-BASED ROTATION ------

class TimeRotatingLogHandler(logging.Handler):
    """Custom log handler that rotates logs based on time and zips old log files."""
    def __init__(self, log_dir, base_filename, rotation_days):
        super().__init__()
        self.log_dir = Path(log_dir)
        self.base_filename = base_filename
        self.rotation_days = rotation_days
        self.current_log_file = None
        self.file_handler = None
        
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._rotate_if_needed()
    
    def _get_current_log_path(self):
        return self.log_dir / self.base_filename
    
    def _get_rotation_marker_path(self):
        return self.log_dir / ".last_rotation_sync"
    
    def _should_rotate(self):
        marker_file = self._get_rotation_marker_path()
        if not marker_file.exists():
            return True
        try:
            with open(marker_file, 'r') as f:
                last_rotation_str = f.read().strip()
                last_rotation = datetime.fromisoformat(last_rotation_str)
            if datetime.now() - last_rotation >= timedelta(days=self.rotation_days):
                return True
        except Exception:
            return True
        return False
    
    def _rotate_if_needed(self):
        current_log = self._get_current_log_path()
        if self._should_rotate() and current_log.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archived_name = f"{current_log.stem}_{timestamp}.log"
            archived_path = self.log_dir / archived_name
            
            if self.file_handler:
                self.file_handler.close()
                self.file_handler = None
            
            shutil.move(str(current_log), str(archived_path))
            compressed_path = self.log_dir / f"{archived_name}.gz"
            with open(archived_path, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            archived_path.unlink()
            
            print(f"Log rotated and compressed: {compressed_path}")
            with open(self._get_rotation_marker_path(), 'w') as f:
                f.write(datetime.now().isoformat())
        
        if not self.file_handler:
            self.file_handler = logging.FileHandler(current_log, mode='a')
            self.file_handler.setFormatter(self.formatter)
    
    def emit(self, record):
        self._rotate_if_needed()
        if self.file_handler:
            self.file_handler.emit(record)
    
    def close(self):
        if self.file_handler:
            self.file_handler.close()
        super().close()

# Set up logging
logger = logging.getLogger('syncBot')
logger.setLevel(getattr(logging, LOG_CONFIG['level']))
logger.handlers.clear()

file_handler = TimeRotatingLogHandler(
    LOG_CONFIG['log_dir'],
    'syncBot.log',
    LOG_CONFIG['rotation_days']
)
file_formatter = logging.Formatter('%(asctime)s 🍌 [%(levelname)s] %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

if LOG_CONFIG.get('console_output', False):
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter('🍌 [%(levelname)s] %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

def sync_log(step, message, level='info', error_code='SUCCESS'):
    """Log messages with banana theme and clear error codes."""
    formatted_message = f"[{error_code}] {step}: {message}"
    if level == 'info':
        logger.info(formatted_message)
    elif level == 'warning':
        logger.warning(formatted_message)
    elif level == 'error':
        logger.error(formatted_message)
    elif level == 'debug':
        logger.debug(formatted_message)

# ------ QUAY API FUNCTIONS ------

def list_all_repositories(registry_config):
    """
    List all repositories in a Quay registry namespace using the API.
    
    Args:
        registry_config: Dictionary with registry URL, namespace, and API token
    
    Returns:
        List of repository names, or empty list on failure
    """
    api_url = f"https://{registry_config['url']}/api/v1/repository"
    params = {
        "namespace": registry_config['organization'],
        "public": "false"
    }
    
    all_repos = []
    page = 1
    
    while True:
        try:
            sync_log("API Call", 
                    f"Fetching repositories page {page} from {registry_config['url']}", 
                    'info', 'API_FETCHING')
            
            # Build curl command
            cmd = [
                "curl", "-s",
                "--max-time", str(OPERATION_CONFIG['api_timeout']),
                "-H", f"Authorization: Bearer {registry_config['api_token']}",
                "-H", "Content-Type: application/json",
                f"{api_url}?namespace={params['namespace']}&public={params['public']}&page={page}"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, 
                                  timeout=OPERATION_CONFIG['api_timeout'])
            
            if result.returncode != 0:
                sync_log("API Call", 
                        f"Failed to fetch repositories: {result.stderr}", 
                        'error', 'API_FAILED')
                break
            
            data = json.loads(result.stdout)
            repos = data.get('repositories', [])
            
            if not repos:
                break
            
            for repo in repos:
                repo_name = repo.get('name')
                if repo_name:
                    all_repos.append(repo_name)
            
            sync_log("API Call", 
                    f"Found {len(repos)} repositories on page {page}", 
                    'info', 'API_PAGE_SUCCESS')
            
            # Check if there are more pages
            if not data.get('has_additional', False):
                break
                
            page += 1
            
        except subprocess.TimeoutExpired:
            sync_log("API Call", 
                    f"API timeout fetching repositories page {page}", 
                    'error', 'API_TIMEOUT')
            break
        except json.JSONDecodeError as e:
            sync_log("API Call", 
                    f"Failed to parse API response: {str(e)}", 
                    'error', 'API_PARSE_ERROR')
            break
        except Exception as e:
            sync_log("API Call", 
                    f"Unexpected error fetching repositories: {str(e)}", 
                    'error', 'API_EXCEPTION')
            break
    
    sync_log("Repository Discovery", 
            f"Total repositories found: {len(all_repos)}", 
            'info', 'REPO_DISCOVERY_COMPLETE')
    
    return all_repos

def list_all_tags(registry_config, repo_name):
    """
    List all tags for a specific repository using Quay API.
    
    Args:
        registry_config: Dictionary with registry URL, namespace, and API token
        repo_name: Repository name
    
    Returns:
        List of tag names, or empty list on failure
    """
    namespace = registry_config['organization']
    api_url = f"https://{registry_config['url']}/api/v1/repository/{namespace}/{repo_name}/tag/"
    
    all_tags = []
    page = 1
    
    while True:
        try:
            cmd = [
                "curl", "-s",
                "--max-time", str(OPERATION_CONFIG['api_timeout']),
                "-H", f"Authorization: Bearer {registry_config['api_token']}",
                "-H", "Content-Type: application/json",
                f"{api_url}?page={page}"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, 
                                  timeout=OPERATION_CONFIG['api_timeout'])
            
            if result.returncode != 0:
                sync_log("Tag Discovery", 
                        f"Failed to fetch tags for {repo_name}: {result.stderr}", 
                        'error', 'TAG_FETCH_FAILED')
                break
            
            data = json.loads(result.stdout)
            tags = data.get('tags', [])
            
            if not tags:
                break
            
            for tag in tags:
                tag_name = tag.get('name')
                if tag_name:
                    all_tags.append(tag_name)
            
            # Check if there are more pages
            if not data.get('has_additional', False):
                break
                
            page += 1
            
        except subprocess.TimeoutExpired:
            sync_log("Tag Discovery", 
                    f"Timeout fetching tags for {repo_name}", 
                    'error', 'TAG_TIMEOUT')
            break
        except json.JSONDecodeError as e:
            sync_log("Tag Discovery", 
                    f"Failed to parse tags for {repo_name}: {str(e)}", 
                    'error', 'TAG_PARSE_ERROR')
            break
        except Exception as e:
            sync_log("Tag Discovery", 
                    f"Error fetching tags for {repo_name}: {str(e)}", 
                    'error', 'TAG_EXCEPTION')
            break
    
    return all_tags

# ------ DOCKER AUTHENTICATION ------

def docker_login_registries():
    """
    Interactively prompt for credentials and login to Prod and DR registries.
    
    Returns:
        True to continue (always, per requirements)
    """
    sync_log("Docker Login", 
            "🍌 Starting authentication to Prod and DR registries", 
            'info', 'LOGIN_START')
    
    print("\n" + "="*70)
    print("DOCKER AUTHENTICATION REQUIRED")
    print("="*70)
    print("syncBot needs to login to Prod and DR registries.")
    print("Please provide credentials for each registry.\n")
    
    registries_to_login = ['prod', 'dr']
    
    for env in registries_to_login:
        if env not in REGISTRIES:
            sync_log("Docker Login", 
                    f"Registry configuration not found for {env}", 
                    'error', 'LOGIN_CONFIG_MISSING')
            continue
        
        config = REGISTRIES[env]
        registry_url = config['url']
        
        print(f"\n{'─'*70}")
        print(f"Registry: {registry_url} ({env} environment)")
        print(f"{'─'*70}")
        
        username = input(f"Username for {registry_url}: ").strip()
        if not username:
            sync_log("Docker Login", 
                    f"No username provided for {registry_url}", 
                    'error', 'LOGIN_NO_USERNAME')
            continue
        
        password = getpass.getpass(f"Password for {registry_url}: ")
        if not password:
            sync_log("Docker Login", 
                    f"No password provided for {registry_url}", 
                    'error', 'LOGIN_NO_PASSWORD')
            continue
        
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
                sync_log("Docker Login", 
                        f"Successfully authenticated to {registry_url}", 
                        'info', 'LOGIN_SUCCESS')
            else:
                error_msg = result.stderr.decode() if result.stderr else "Unknown error"
                print(f"Failed to login to {registry_url}: {error_msg}")
                sync_log("Docker Login", 
                        f"Authentication failed for {registry_url}: {error_msg}", 
                        'error', 'LOGIN_FAILED')
                
        except subprocess.TimeoutExpired:
            print(f"Login timeout for {registry_url}")
            sync_log("Docker Login", 
                    f"Login timeout for {registry_url}", 
                    'error', 'LOGIN_TIMEOUT')
        except Exception as e:
            print(f"Unexpected error logging in to {registry_url}: {str(e)}")
            sync_log("Docker Login", 
                    f"Unexpected login error for {registry_url}: {str(e)}", 
                    'error', 'LOGIN_EXCEPTION')
    
    print("\n" + "="*70)
    print("Authentication complete - proceeding with sync")
    sync_log("Docker Login", 
            "Authentication phase completed", 
            'info', 'LOGIN_COMPLETE')
    print("="*70 + "\n")
    
    return True

# ------ DOCKER OPERATIONS ------

def run_docker(*args):
    """
    Run docker commands with proper error handling and retries.
    
    Args:
        *args: Docker command arguments
    
    Returns:
        True if command succeeded, False if failed
    """
    cmd = ["docker"] + list(args)
    cmd_str = ' '.join(cmd)
    
    for attempt in range(OPERATION_CONFIG['max_retries']):
        try:
            sync_log("Docker Command", 
                    f"Attempt {attempt + 1}: {cmd_str}", 
                    'debug', 'DOCKER_RUNNING')
            
            start_time = time.time()
            subprocess.run(cmd, check=True, capture_output=True, text=True, 
                          timeout=OPERATION_CONFIG['docker_timeout'])
            
            duration = time.time() - start_time
            sync_log("Docker Command", 
                    f"Command successful: {cmd_str} ({duration:.2f}s)", 
                    'debug', 'DOCKER_SUCCESS')
            return True
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if hasattr(e, 'stderr') else str(e)
            sync_log("Docker Command", 
                    f"Command failed: {cmd_str} | Error: {error_msg}", 
                    'error', f'DOCKER_EXIT_{e.returncode}')
            
            if e.returncode in [125, 1] and "not found" in str(error_msg).lower():
                sync_log("Docker Command", 
                        f"Image not found, skipping retries: {cmd_str}", 
                        'error', 'DOCKER_NOT_FOUND')
                return False
            
            if attempt < OPERATION_CONFIG['max_retries'] - 1:
                sync_log("Docker Command", 
                        f"Retrying in {OPERATION_CONFIG['retry_delay']}s", 
                        'info', 'DOCKER_RETRY')
                time.sleep(OPERATION_CONFIG['retry_delay'])
            else:
                return False
                
        except subprocess.TimeoutExpired:
            sync_log("Docker Command", 
                    f"Command timeout: {cmd_str}", 
                    'error', 'DOCKER_TIMEOUT')
            if attempt < OPERATION_CONFIG['max_retries'] - 1:
                time.sleep(OPERATION_CONFIG['retry_delay'])
            else:
                return False
                
        except Exception as e:
            sync_log("Docker Command", 
                    f"Unexpected error: {cmd_str} | {str(e)}", 
                    'error', 'DOCKER_EXCEPTION')
            if attempt < OPERATION_CONFIG['max_retries'] - 1:
                time.sleep(OPERATION_CONFIG['retry_delay'])
            else:
                return False
    
    return False

def image_exists_in_registry(image_url):
    """
    Check if an image:tag already exists in the registry.
    
    Args:
        image_url: Full image URL including tag
    
    Returns:
        True if image exists, False otherwise
    """
    try:
        cmd = ["docker", "manifest", "inspect", image_url]
        result = subprocess.run(cmd, capture_output=True, timeout=30, text=True)
        
        if result.returncode == 0:
            sync_log("Image Check", 
                    f"Image exists in registry: {image_url}", 
                    'debug', 'IMAGE_EXISTS')
            return True
        else:
            sync_log("Image Check", 
                    f"Image not found in registry: {image_url}", 
                    'debug', 'IMAGE_NOT_EXISTS')
            return False
            
    except subprocess.TimeoutExpired:
        sync_log("Image Check", 
                f"Timeout checking image existence: {image_url}", 
                'warning', 'IMAGE_CHECK_TIMEOUT')
        return False
    except Exception as e:
        sync_log("Image Check", 
                f"Error checking image existence: {image_url} - {str(e)}", 
                'warning', 'IMAGE_CHECK_ERROR')
        return False

def cleanup_local_images(image_list):
    """
    Remove all local copies of images.
    
    Args:
        image_list: List of image URLs to remove
    """
    sync_log("Cleanup", 
            f"Removing {len(image_list)} local image(s)", 
            'info', 'CLEANUP_START')
    
    for image in image_list:
        run_docker("rmi", "-f", image)
    
    sync_log("Cleanup", 
            "Local cleanup complete", 
            'info', 'CLEANUP_DONE')

# ------ MAIN SYNC FUNCTION ------

def sync_image(prod_image, dr_image):
    """
    Sync a single image from Prod to DR with verification.
    
    Args:
        prod_image: Source image URL (Prod)
        dr_image: Destination image URL (DR)
    
    Returns:
        True if sync successful, False otherwise
    """
    local_images = []
    
    try:
        # Step 1: Check if image already exists in DR
        if image_exists_in_registry(dr_image):
            sync_log("Image Sync", 
                    f"Image already exists in DR, skipping: {dr_image}", 
                    'info', 'SYNC_ALREADY_EXISTS')
            return True
        
        # Step 2: Pull from Prod
        sync_log("Image Sync", 
                f"Pulling from Prod: {prod_image}", 
                'info', 'SYNC_PULLING')
        
        if not run_docker("pull", prod_image):
            sync_log("Image Sync", 
                    f"Failed to pull from Prod: {prod_image}", 
                    'error', 'SYNC_PULL_FAILED')
            return False
        
        local_images.append(prod_image)
        
        # Step 3: Tag for DR
        sync_log("Image Sync", 
                f"Tagging for DR: {dr_image}", 
                'info', 'SYNC_TAGGING')
        
        if not run_docker("tag", prod_image, dr_image):
            sync_log("Image Sync", 
                    f"Failed to tag for DR: {dr_image}", 
                    'error', 'SYNC_TAG_FAILED')
            cleanup_local_images(local_images)
            return False
        
        local_images.append(dr_image)
        
        # Step 4: Push to DR
        sync_log("Image Sync", 
                f"Pushing to DR: {dr_image}", 
                'info', 'SYNC_PUSHING')
        
        if not run_docker("push", dr_image):
            sync_log("Image Sync", 
                    f"Failed to push to DR: {dr_image}", 
                    'error', 'SYNC_PUSH_FAILED')
            cleanup_local_images(local_images)
            return False
        
        # Step 5: Verify in DR
        sync_log("Image Sync", 
                f"Verifying in DR: {dr_image}", 
                'info', 'SYNC_VERIFYING')
        
        if not image_exists_in_registry(dr_image):
            sync_log("Image Sync", 
                    f"Verification failed - image not found in DR after push: {dr_image}", 
                    'error', 'SYNC_VERIFY_FAILED')
            cleanup_local_images(local_images)
            return False
        
        # Step 6: Cleanup local images
        cleanup_local_images(local_images)
        
        sync_log("Image Sync", 
                f"Successfully synced: {prod_image} -> {dr_image}", 
                'info', 'SYNC_SUCCESS')
        
        return True
        
    except Exception as e:
        sync_log("Image Sync", 
                f"Unexpected error syncing {prod_image}: {str(e)}", 
                'error', 'SYNC_EXCEPTION')
        
        # Cleanup on exception
        if local_images:
            cleanup_local_images(local_images)
        
        return False

# ------ MAIN SCRIPT EXECUTION ------

def main():
    """Main function that orchestrates the entire sync process."""
    start_time = time.time()
    
    sync_log("syncBot Startup", 
            "🍌 syncBot 1.0 starting up", 
            'info', 'STARTUP')
    
    # Step 1: Validate configuration
    if 'prod' not in REGISTRIES or 'dr' not in REGISTRIES:
        sync_log("Configuration Check", 
                "Missing prod or dr registry configuration", 
                'error', 'CONFIG_MISSING')
        print("Error: prod and dr registries must be configured in banannaBot_config.py")
        return 1
    
    prod_config = REGISTRIES['prod']
    dr_config = REGISTRIES['dr']
    
    sync_log("Configuration Check", 
            "🍌 Configuration validated", 
            'info', 'CONFIG_VALID')
    
    # Step 2: Docker login
    docker_login_registries()
    
    # Step 3: Discover all repositories in Prod
    sync_log("Repository Discovery", 
            "🍌 Discovering all repositories in Prod registry", 
            'info', 'DISCOVERY_START')
    
    repositories = list_all_repositories(prod_config)
    
    if not repositories:
        sync_log("Repository Discovery", 
                "No repositories found in Prod", 
                'warning', 'DISCOVERY_EMPTY')
        print("No repositories found in Prod registry.")
        return 1
    
    sync_log("Repository Discovery", 
            f"Found {len(repositories)} repositories to sync", 
            'info', 'DISCOVERY_COMPLETE')
    
    # Step 4: Initialize tracking
    total_repos = len(repositories)
    total_images = 0
    successful_images = 0
    failed_images = 0
    skipped_images = 0
    
    # Step 5: Process each repository
    for repo_idx, repo_name in enumerate(repositories, 1):
        sync_log("Repository Processing", 
                f"🍌 [{repo_idx}/{total_repos}] Processing repository: {repo_name}", 
                'info', 'REPO_PROCESSING')
        
        # Get all tags for this repository
        tags = list_all_tags(prod_config, repo_name)
        
        if not tags:
            sync_log("Repository Processing", 
                    f"No tags found for repository: {repo_name}", 
                    'warning', 'REPO_NO_TAGS')
            continue
        
        sync_log("Repository Processing", 
                f"Found {len(tags)} tag(s) in {repo_name}", 
                'info', 'REPO_TAGS_FOUND')
        
        # Process each tag
        for tag_idx, tag in enumerate(tags, 1):
            total_images += 1
            
            # Construct image URLs
            prod_image = f"{prod_config['url']}/{prod_config['namespace']}/{repo_name}:{tag}"
            dr_image = f"{dr_config['url']}/{dr_config['namespace']}/{repo_name}:{tag}"
            
            sync_log("Image Processing", 
                    f"[{repo_idx}/{total_repos}][{tag_idx}/{len(tags)}] Syncing: {repo_name}:{tag}", 
                    'info', 'IMAGE_PROCESSING')
            
            # Sync the image
            success = sync_image(prod_image, dr_image)
            
            if success:
                if image_exists_in_registry(dr_image):
                    successful_images += 1
                else:
                    skipped_images += 1
            else:
                failed_images += 1
        
        # Progress update after each repo
        progress = (repo_idx / total_repos) * 100
        sync_log("Progress", 
                f"Repository {repo_idx}/{total_repos} complete ({progress:.1f}%) | " +
                f"Images: {successful_images} success, {skipped_images} skipped, {failed_images} failed", 
                'info', 'PROGRESS_UPDATE')
    
    # Step 6: Final statistics
    duration = time.time() - start_time
    success_rate = (successful_images / total_images * 100) if total_images > 0 else 0
    
    sync_log("Final Statistics", 
            "🍌 SYNC OPERATION COMPLETE", 
            'info', 'STATS_HEADER')
    sync_log("Final Statistics", 
            f"Total duration: {duration:.2f} seconds ({duration/60:.2f} minutes)", 
            'info', 'STATS_DURATION')
    sync_log("Final Statistics", 
            f"Repositories processed: {total_repos}", 
            'info', 'STATS_REPOS')
    sync_log("Final Statistics", 
            f"Total images processed: {total_images}", 
            'info', 'STATS_TOTAL')
    sync_log("Final Statistics", 
            f"Successfully synced: {successful_images}", 
            'info', 'STATS_SUCCESS')
    sync_log("Final Statistics", 
            f"Already existed (skipped): {skipped_images}", 
            'info', 'STATS_SKIPPED')
    sync_log("Final Statistics", 
            f"Failed: {failed_images}", 
            'info', 'STATS_FAILED')
    sync_log("Final Statistics", 
            f"Success rate: {success_rate:.1f}%", 
            'info', 'STATS_RATE')
    
    # Step 7: Final status
    if failed_images == 0:
        sync_log("Sync Complete", 
                f"All {total_images} images synced successfully from Prod to DR", 
                'info', 'SYNC_COMPLETE_SUCCESS')
        return 0
    else:
        sync_log("Sync Complete", 
                f"Sync completed with errors: {successful_images}/{total_images} successful", 
                'warning', 'SYNC_COMPLETE_PARTIAL')
        return 1

# ------ SCRIPT ENTRY POINT ------
if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        sync_log("User Interrupt", 
                "syncBot received stop signal from user - shutting down gracefully", 
                'info', 'USER_STOP')
        sys.exit(130)
    except Exception as e:
        sync_log("Fatal Error", 
                f"syncBot encountered fatal error: {str(e)}", 
                'error', 'FATAL_ERROR')
        sys.exit(1)
