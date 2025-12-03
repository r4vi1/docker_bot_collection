# syncBot - Registry Sync Script

## Overview
syncBot is a production-ready script that synchronizes ALL images from Prod registry to DR registry, creating a perfect one-to-one mirror. It uses Quay API to discover all repositories and tags, then systematically syncs each image with comprehensive verification and error handling.

## Version
**1.0**

## Author
Ravi Varma

## Purpose
Sync all images from:
- **Source:** Prod registry (`quay-registry.apps.ocpcorpprod.icicibankltd.com`)
- **Destination:** DR registry (`quay-registry.apps.ocpcorpdr.icicibankltd.com`)

## Features

### Core Functionality
1. **Quay API Discovery**
   - Lists ALL repositories in Prod namespace
   - Gets ALL tags for each repository
   - Handles pagination automatically
   - Designed for large-scale operations (270+ repos)

2. **Smart Sync Process**
   - Checks if image already exists in DR before pulling
   - Pulls from Prod only if needed
   - Tags for DR registry
   - Pushes to DR
   - Verifies image exists in DR after push
   - Cleans up local images (both tagged and original)

3. **Production-Ready**
   - Multiple retries on failure
   - Continues on errors (doesn't stop for one failure)
   - Comprehensive error logging with error codes
   - Progress tracking for long-running operations
   - Time-based log rotation

4. **Safety Features**
   - Post-push verification before local cleanup
   - Skips images that already exist in DR
   - Never overwrites existing images
   - Cleans up on errors to prevent disk space issues

## Configuration

Uses existing `banannaBot_config.py`:
- Reads `REGISTRIES['prod']` and `REGISTRIES['dr']`
- Uses `LOG_CONFIG` for logging settings
- Uses `OPERATION_CONFIG` for retry/timeout settings

**No additional configuration needed!**

## Usage

### Run the Script
```bash
python3 syncBot.py
```

### What Happens

1. **Startup & Validation**
   - Validates prod/dr configs exist
   - Logs startup message

2. **Authentication**
   - Prompts for Prod registry credentials
   - Prompts for DR registry credentials
   - Performs docker login for both

3. **Discovery Phase**
   - Uses Quay API to list all repos in Prod
   - For each repo, gets all tags
   - Example output: "Found 270 repositories to sync"

4. **Sync Phase**
   - For each image:tag combination:
     - Check if exists in DR → Skip if yes
     - Pull from Prod
     - Tag for DR
     - Push to DR
     - Verify in DR
     - Delete local copies
   
5. **Progress Updates**
   - After each repo: "Repository 50/270 complete (18.5%)"
   - Shows success/skipped/failed counts

6. **Final Report**
   - Total duration
   - Repositories processed
   - Images synced/skipped/failed
   - Success rate

## Workflow Example

```
Prod Image:  quay-registry.apps.ocpcorpprod.icicibankltd.com/
             apigee_hybrid_dmz_prod/tsg1-apigee-anthos-prod/
             trafficreports-prod:7ad5aab

                      ↓ (syncBot)

DR Image:    quay-registry.apps.ocpcorpdr.icicibankltd.com/
             apigee_hybrid_dmz_prod/tsg1-apigee-anthos-prod/
             trafficreports-prod:7ad5aab
```

## Log Files

### Location
```
/Users/ravivarma/Documents/logs/
├── syncBot.log                      # Current log
├── .last_rotation_sync              # Rotation marker
├── syncBot_20251006_120000.log.gz   # Archived logs
└── syncBot_20251013_120000.log.gz   # Archived logs
```

### Log Format
```
2025-10-06 05:30:00 🍌 [INFO] [STARTUP] syncBot Startup: 🍌 syncBot 1.0 starting up
2025-10-06 05:30:15 🍌 [INFO] [DISCOVERY_COMPLETE] Repository Discovery: Found 270 repositories
2025-10-06 05:30:20 🍌 [INFO] [SYNC_SUCCESS] Image Sync: Successfully synced: prod-image -> dr-image
```

### Key Error Codes
- `API_*` - Quay API operations (fetching repos/tags)
- `LOGIN_*` - Docker authentication
- `SYNC_*` - Image sync operations
- `DOCKER_*` - Docker command execution
- `IMAGE_*` - Image existence checks
- `PROGRESS_UPDATE` - Progress tracking

## Performance Expectations

For **270 repositories** with average **3 tags each** (810 images):

- **Already in DR (skipped):** ~1-2 seconds per image
- **Need sync:** ~30-60 seconds per image (depends on size)
- **Estimated total time:** 2-8 hours (varies with image sizes and network)

The script shows progress after each repository so you can monitor.

## Error Handling

### Continues On Errors
The script **always continues** if an image fails:
- Logs the error with clear error code
- Moves to next image
- Reports failures in final statistics

### Automatic Retries
- Docker commands: 3 retries with 5s delay
- Timeouts: 300s for docker operations, 30s for API calls
- All configurable in `banannaBot_config.py`

### Safety Mechanisms
1. **Pre-push check:** Skips if image already in DR
2. **Post-push verification:** Verifies in DR before local cleanup
3. **Cleanup on failure:** Removes local images even if sync fails
4. **Forced removal:** Uses `docker rmi -f` to ensure cleanup

## Common Scenarios

### First Run (No images in DR)
- Syncs ALL images from Prod to DR
- May take several hours
- Progress tracked and logged

### Subsequent Runs (Most images exist)
- Skips existing images quickly (~1-2s each)
- Only syncs new images
- Much faster than first run

### Interrupted Run
- Safe to restart - skips already synced images
- Continues from where network/error occurred
- No duplicate work

## Verification

After syncBot completes, verify with:

```bash
# Check DR registry has images
docker search quay-registry.apps.ocpcorpdr.icicibankltd.com/...

# Check specific image
docker manifest inspect quay-registry.apps.ocpcorpdr.icicibankltd.com/...
```

## Troubleshooting

### Check Logs
```bash
tail -f logs/syncBot.log
```

### Common Issues

**"No repositories found in Prod"**
- Check Prod API token in `banannaBot_config.py`
- Verify namespace name is correct
- Check API token has read permissions

**"Failed to pull from Prod"**
- Check docker login succeeded
- Verify image actually exists in Prod
- Check network connectivity

**"Verification failed - image not found in DR after push"**
- Check DR registry connectivity
- Verify docker login to DR succeeded
- May indicate push succeeded but verification timing issue (rare)

**Script running slowly**
- Normal for large images
- Check docker daemon resource usage
- Monitor network bandwidth

### Debug Mode
Edit `banannaBot_config.py`:
```python
LOG_CONFIG = {
    "level": "DEBUG",  # More verbose logging
    ...
}
```

## Safety Notes

1. **Disk Space:** Script cleans up immediately after each image, but ensure adequate space for largest image
2. **Network:** Long-running operation, ensure stable network connection
3. **Credentials:** Passwords entered interactively (hidden from display)
4. **Non-Destructive:** Never deletes anything from registries, only local images

## Comparison with banannaBot

| Feature | banannaBot | syncBot |
|---------|-----------|---------|
| **Purpose** | Mirror specific images | Sync ALL Prod → DR |
| **Image Selection** | Manual config list | Automatic discovery |
| **Scale** | Few images | 270+ repos |
| **Source** | Any registry | Prod only |
| **Destination** | Multiple targets | DR only |
| **Use Case** | Regular deployments | DR synchronization |

## Best Practices

1. **Schedule:** Run weekly or after major Prod deployments
2. **Monitor:** Check logs for failures
3. **Verify:** Spot-check critical images in DR
4. **Cleanup:** Old compressed logs can be archived/removed periodically
5. **Test:** Do a dry run on small subset first if nervous

## Exit Codes

- `0` - All images synced successfully
- `1` - Some images failed (but others succeeded)
- `130` - User interrupted (Ctrl+C)

## Support

For issues:
1. Check `logs/syncBot.log` for detailed error messages
2. Look for error codes in logs (e.g., `SYNC_PULL_FAILED`)
3. Verify registry connectivity and credentials
4. Check disk space and docker daemon status

---

**Ready to sync?** Run `python3 syncBot.py` and grab coffee - it'll take a while for 270+ repos! ☕
