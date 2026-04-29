#!/bin/bash

# Helper script to change the UUID of the backup drive
# This resolves the issue when both drives have identical UUIDs

echo "========================================="
echo "Backup Drive UUID Changer"
echo "========================================="
echo ""
echo "WARNING: This will change the filesystem UUID of your backup drive."
echo "Make sure you select the CORRECT drive!"
echo ""

# Show currently connected drives
echo "Currently connected drives:"
echo ""
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,LABEL,UUID,FSTYPE | grep -v "loop"
echo ""
echo "========================================="
echo ""

# Function to change UUID based on filesystem type
change_uuid() {
    local device=$1
    local fstype=$2

    echo "Changing UUID for $device (filesystem: $fstype)..."

    case $fstype in
        ext4|ext3|ext2)
            echo "Generating new UUID for ext filesystem..."
            sudo tune2fs -U random "$device"
            ;;
        ntfs)
            echo "For NTFS, you need ntfslabel from ntfs-3g package"
            echo "Command: sudo ntfslabel --new-serial $device"
            ;;
        exfat)
            echo "For exFAT, you need exfatlabel from exfatprogs package"
            echo "Unmount first, then: sudo exfatlabel -i $device"
            ;;
        vfat|fat32)
            echo "For FAT32, you need mlabel from mtools package"
            echo "This is more complex. Consider reformatting or using a different method."
            ;;
        *)
            echo "Unsupported filesystem type: $fstype"
            return 1
            ;;
    esac

    return 0
}

echo "Steps to change your backup drive UUID:"
echo ""
echo "1. IDENTIFY which drive is your BACKUP (check by mount point or size)"
echo "   Look at the output above to find your backup drive device (e.g., /dev/sdb1)"
echo ""
echo "2. UNMOUNT the backup drive if it's mounted:"
echo "   sudo umount /dev/sdX1  (replace X with correct letter)"
echo ""
echo "3. CHANGE the UUID based on filesystem type:"
echo ""
echo "   For ext4/ext3/ext2:"
echo "   sudo tune2fs -U random /dev/sdX1"
echo ""
echo "   For NTFS:"
echo "   sudo ntfslabel --new-serial /dev/sdX1"
echo ""
echo "   For exFAT:"
echo "   sudo exfatlabel -i /dev/sdX1"
echo ""
echo "4. VERIFY the new UUID:"
echo "   sudo blkid /dev/sdX1"
echo ""
echo "5. UPDATE sync-drives.sh with the new BACKUP_UUID"
echo ""
echo "========================================="
echo ""

read -p "Do you want help identifying the filesystem type of a specific drive? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    read -p "Enter the device path (e.g., /dev/sdb1): " device

    if [ -b "$device" ]; then
        echo ""
        echo "Device information for $device:"
        sudo blkid "$device"
        echo ""

        fstype=$(lsblk -no FSTYPE "$device")
        echo "Filesystem type: $fstype"
        echo ""

        read -p "Is this your BACKUP drive that you want to change? (yes/no) " -r
        echo ""

        if [[ $REPLY == "yes" ]]; then
            # Check if mounted
            if mount | grep -q "$device"; then
                mountpoint=$(mount | grep "$device" | awk '{print $3}')
                echo "Drive is currently mounted at: $mountpoint"
                read -p "Unmount it now? (y/n) " -n 1 -r
                echo ""

                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    sudo umount "$device"
                    echo "Unmounted successfully"
                else
                    echo "Please unmount manually: sudo umount $device"
                    exit 1
                fi
            fi

            echo ""
            echo "Ready to change UUID..."
            read -p "Proceed with changing UUID? (yes/no) " -r
            echo ""

            if [[ $REPLY == "yes" ]]; then
                change_uuid "$device" "$fstype"

                echo ""
                echo "New UUID:"
                sudo blkid "$device" | grep -o 'UUID="[^"]*"'
                echo ""
                echo "Done! Copy this UUID to sync-drives.sh as BACKUP_UUID"
            else
                echo "Cancelled."
            fi
        else
            echo "Cancelled for safety."
        fi
    else
        echo "Error: $device is not a valid block device"
    fi
fi

echo ""
echo "Script finished."
