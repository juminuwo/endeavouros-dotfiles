# External Drive Sync Setup Guide

This directory contains scripts to automatically mount and sync your external hard drives.

## Files

- `sync-drives.sh` - Main sync script (mounts drives and syncs main to backup)
- `find-drive-uuids.sh` - Helper script to identify your drive UUIDs
- `DRIVE-SYNC-SETUP.md` - This file

## Initial Setup

### 1. Find Your Drive UUIDs

Connect both external drives and run:

```bash
./find-drive-uuids.sh
```

Or manually check:

```bash
lsblk -f
# or
sudo blkid
```

Identify your Main and Backup drives and note their UUIDs.

### 2. Configure the Sync Script

Edit `sync-drives.sh` and update the configuration section:

```bash
nano sync-drives.sh
```

Set these values:
- `MAIN_UUID="your-main-drive-uuid-here"`
- `BACKUP_UUID="your-backup-drive-uuid-here"`

Optionally adjust:
- `MAIN_MOUNT` and `BACKUP_MOUNT` paths
- `LOG_FILE` location

### 3. Create Log Directory

```bash
sudo touch /var/log/drive-sync.log
sudo chown howis:howis /var/log/drive-sync.log
```

### 4. Test the Script

Run manually first to ensure it works:

```bash
./sync-drives.sh
```

Check the log:

```bash
cat /var/log/drive-sync.log
```

## Setting Up a Cron Job

### Option 1: Run Daily at 2 AM

Edit your crontab:

```bash
crontab -e
```

Add this line:

```cron
0 2 * * * /home/howis/git/linux-utils/sync-drives.sh
```

### Option 2: Run Weekly (Sundays at 3 AM)

```cron
0 3 * * 0 /home/howis/git/linux-utils/sync-drives.sh
```

### Option 3: Run on System Startup

```cron
@reboot sleep 60 && /home/howis/git/linux-utils/sync-drives.sh
```

The `sleep 60` ensures drives have time to be recognized after boot.

## How It Works

1. **Drive Identification**: Uses UUIDs to reliably identify drives (works even if device names like /dev/sdb change)
2. **Auto-Mount**: Checks if drives are already mounted, mounts them if needed
3. **Safety Checks**: Verifies drives are connected and mounted before syncing
4. **Mirror Sync**: Uses rsync with `--delete` to make backup an exact copy of main
5. **Logging**: All operations logged to `/var/log/drive-sync.log`

## Sync Behavior

The script uses rsync with these options:
- `-a`: Archive mode (preserves permissions, timestamps, symlinks)
- `-v`: Verbose output
- `--delete`: Files deleted from Main will be deleted from Backup (true mirror)
- Excludes: `.Trash-*`, `lost+found`, `.tmp*`

**Important**: This is a one-way sync from Main → Backup. Files deleted from Main will be deleted from Backup.

## Troubleshooting

### Drives not found

- Ensure both drives are connected
- Verify UUIDs are correct: `sudo blkid`
- Check if drives are already mounted: `mount | grep UUID`

### Permission errors

- The script uses `sudo` for mount operations
- You may need to add your user to sudoers with NOPASSWD for mount commands
- Or run the script with sudo: `sudo ./sync-drives.sh`

### Mount points already in use

If mount points exist from previous mounts:
```bash
sudo umount /run/media/howis/Main
sudo umount /run/media/howis/Backup
```

## Manual Operations

### Unmount drives after sync

```bash
sudo umount /run/media/howis/Main
sudo umount /run/media/howis/Backup
```

### Dry run (see what would be synced without making changes)

Edit the script and add `--dry-run` to the rsync command temporarily.

### Check sync status

```bash
tail -f /var/log/drive-sync.log
```
