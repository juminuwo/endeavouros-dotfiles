# Systemd Timer Setup for Drive Sync

This guide shows how to set up automatic drive syncing using systemd timers (recommended for Arch-based systems like EndeavorOS).

## Files Created

- `drive-sync.service` - Systemd service unit
- `drive-sync.timer` - Systemd timer unit (runs every Sunday at 5 AM)

## Installation Steps

### 1. Ensure the sync script is configured

Make sure you've already:
- Set the UUIDs in `sync-drives.sh`
- Tested the script manually: `./sync-drives.sh`

### 2. Copy systemd files to system directory

```bash
sudo cp drive-sync.service /etc/systemd/system/
sudo cp drive-sync.timer /etc/systemd/system/
```

### 3. Set correct permissions

```bash
sudo chmod 644 /etc/systemd/system/drive-sync.service
sudo chmod 644 /etc/systemd/system/drive-sync.timer
```

### 4. Reload systemd to recognize new units

```bash
sudo systemctl daemon-reload
```

### 5. Enable and start the timer

```bash
sudo systemctl enable drive-sync.timer
sudo systemctl start drive-sync.timer
```

## Verify Setup

### Check timer status

```bash
systemctl status drive-sync.timer
```

### List all timers and find yours

```bash
systemctl list-timers
```

This shows when it will run next.

### Check service status

```bash
systemctl status drive-sync.service
```

## View Logs

### View recent logs

```bash
journalctl -u drive-sync.service
```

### Follow logs in real-time

```bash
journalctl -u drive-sync.service -f
```

### View logs since last boot

```bash
journalctl -u drive-sync.service -b
```

### View logs from last run

```bash
journalctl -u drive-sync.service -n 50
```

## Manual Operations

### Run the sync manually (without waiting for timer)

```bash
sudo systemctl start drive-sync.service
```

### Stop the timer

```bash
sudo systemctl stop drive-sync.timer
```

### Disable the timer (prevent auto-start on boot)

```bash
sudo systemctl disable drive-sync.timer
```

### Re-enable after changes

```bash
sudo systemctl daemon-reload
sudo systemctl restart drive-sync.timer
```

## Customizing the Schedule

Edit the timer file to change when it runs:

```bash
sudo nano /etc/systemd/system/drive-sync.timer
```

### Example Schedules

**Daily at 2 AM:**
```ini
OnCalendar=*-*-* 02:00:00
```

**Mondays and Fridays at 3 AM:**
```ini
OnCalendar=Mon,Fri *-*-* 03:00:00
```

**Every 6 hours:**
```ini
OnCalendar=*-*-* 00/6:00:00
```

**First day of every month at midnight:**
```ini
OnCalendar=*-*-01 00:00:00
```

After editing, reload:
```bash
sudo systemctl daemon-reload
sudo systemctl restart drive-sync.timer
```

## Testing the Schedule

To test when the timer would trigger:

```bash
systemd-analyze calendar "Sun *-*-* 05:00:00"
```

This shows the next several times it would run.

## Troubleshooting

### Timer not running

1. Check if timer is active:
   ```bash
   systemctl is-active drive-sync.timer
   ```

2. Check if timer is enabled:
   ```bash
   systemctl is-enabled drive-sync.timer
   ```

3. View timer details:
   ```bash
   systemctl cat drive-sync.timer
   ```

### Service fails to run

1. Check the service status:
   ```bash
   systemctl status drive-sync.service
   ```

2. View detailed logs:
   ```bash
   journalctl -u drive-sync.service -xe
   ```

3. Test the script manually:
   ```bash
   /home/howis/git/linux-utils/sync-drives.sh
   ```

### Permissions issues

The service runs as user `howis` but uses `sudo` for mount operations. Ensure your user can run mount commands via sudo.

To allow passwordless sudo for mount (optional):

```bash
sudo visudo
```

Add:
```
howis ALL=(ALL) NOPASSWD: /usr/bin/mount, /usr/bin/umount, /usr/bin/rsync
```

## Email Notifications on Failure

To get emails when the sync fails, install and configure:

```bash
sudo pacman -S mailutils
```

Then add to the `[Service]` section of `drive-sync.service`:
```ini
OnFailure=status-email@%n.service
```

## Advantages of Systemd Timers

- ✅ Better logging via `journalctl`
- ✅ Persistent (runs missed jobs after system was off)
- ✅ Can depend on other services
- ✅ More flexible scheduling
- ✅ Native to systemd-based systems
- ✅ Can send notifications on failure
- ✅ Easy to monitor and debug

## Removing the Setup

If you want to remove the systemd timer:

```bash
sudo systemctl stop drive-sync.timer
sudo systemctl disable drive-sync.timer
sudo rm /etc/systemd/system/drive-sync.service
sudo rm /etc/systemd/system/drive-sync.timer
sudo systemctl daemon-reload
```
