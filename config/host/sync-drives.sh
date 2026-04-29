#!/bin/bash

# External Drive Sync Script
# Mounts two USB drives and syncs main drive to backup drive

set -e # Exit on error

# ============================================================================
# CONFIGURATION - UPDATE THESE VALUES
# ============================================================================

# To find your drive UUIDs, run: lsblk -f
# or: blkid | grep UUID=
MAIN_UUID="02608207608201A1"   # UUID of your main drive
BACKUP_UUID="5A2EC9DF7D5A6088" # UUID of your backup drive

# Mount points
MAIN_MOUNT="/mnt/Main"
BACKUP_MOUNT="/mnt/Backup"

# User for mount ownership
MOUNT_USER="howis"

# Log file location
LOG_FILE="/home/howis/.local/log/drive-sync.log"

# ============================================================================
# FUNCTIONS
# ============================================================================

# Conditional sudo - only use sudo if not running as root
run_as_root() {
  if [ "$EUID" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

error_exit() {
  log "ERROR: $1"
  exit 1
}

check_uuid_configured() {
  if [ -z "$MAIN_UUID" ] || [ -z "$BACKUP_UUID" ]; then
    error_exit "UUIDs not configured. Please edit this script and set MAIN_UUID and BACKUP_UUID"
  fi
}

get_device_by_uuid() {
  local uuid=$1
  local device=$(blkid -U "$uuid" 2>/dev/null)

  if [ -z "$device" ]; then
    return 1
  fi
  echo "$device"
  return 0
}

is_mounted() {
  local uuid=$1
  local device=$(blkid -U "$uuid" 2>/dev/null)

  if [ -z "$device" ]; then
    return 1
  fi

  # Check if the device is mounted
  mount | grep -q "^$device "
  return $?
}

mount_drive() {
  local uuid=$1
  local mount_point=$2
  local drive_name=$3

  log "Checking $drive_name drive (UUID: $uuid)..."

  # Check if already mounted
  if is_mounted "$uuid"; then
    log "$drive_name drive is already mounted"
    return 0
  fi

  # Get device path
  local device
  if ! device=$(get_device_by_uuid "$uuid"); then
    error_exit "$drive_name drive (UUID: $uuid) not found. Is it connected?"
  fi

  log "Found $drive_name drive at $device"

  # Create mount point if it doesn't exist
  if [ ! -d "$mount_point" ]; then
    log "Creating mount point: $mount_point"
    run_as_root mkdir -p "$mount_point"
  fi

  # Mount the drive
  log "Mounting $drive_name drive to $mount_point..."
  if run_as_root mount -o uid=$(id -u $MOUNT_USER),gid=$(id -g $MOUNT_USER) "$device" "$mount_point"; then
    log "$drive_name drive mounted successfully"
    return 0
  else
    error_exit "Failed to mount $drive_name drive"
  fi
}

verify_mount_contents() {
  local mount_point=$1
  local drive_name=$2

  # Check if mount point has files (basic sanity check)
  if [ ! -d "$mount_point" ] || [ ! "$(ls -A $mount_point 2>/dev/null)" ]; then
    error_exit "$drive_name drive appears to be empty or not mounted correctly at $mount_point"
  fi

  log "$drive_name drive verified at $mount_point"
}

sync_drives() {
  log "Starting sync from Main to Backup..."
  log "Source: $MAIN_MOUNT"
  log "Destination: $BACKUP_MOUNT"

  # Perform the sync with rsync
  # -a: archive mode (preserves permissions, timestamps, etc.)
  # -v: verbose
  # --delete: remove files from backup that don't exist on main
  # --stats: show transfer statistics
  # --exclude: exclude common temporary/system files

  if run_as_root rsync -av --delete --stats \
    --exclude='.Trash-*' \
    --exclude='lost+found' \
    --exclude='.tmp*' \
    "$MAIN_MOUNT/" "$BACKUP_MOUNT/" | tee -a "$LOG_FILE"; then
    log "Sync completed successfully"
    return 0
  else
    error_exit "Sync failed"
  fi
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

log "========================================="
log "Drive Sync Script Started"
log "========================================="

# Check if running with appropriate permissions
if [ "$EUID" -eq 0 ]; then
  log "Running as root"
else
  log "Running as user $(whoami), will use sudo for mount operations"
fi

# Verify UUIDs are configured
check_uuid_configured

# Mount both drives
mount_drive "$MAIN_UUID" "$MAIN_MOUNT" "Main"
mount_drive "$BACKUP_UUID" "$BACKUP_MOUNT" "Backup"

# Verify both drives have content
verify_mount_contents "$MAIN_MOUNT" "Main"
verify_mount_contents "$BACKUP_MOUNT" "Backup"

# Perform the sync
sync_drives

log "========================================="
log "Drive Sync Script Completed Successfully"
log "========================================="

exit 0
