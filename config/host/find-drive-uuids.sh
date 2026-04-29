#!/bin/bash

# Helper script to identify your external drive UUIDs
# Run this script with both drives connected

echo "========================================="
echo "External Drive UUID Finder"
echo "========================================="
echo ""
echo "All connected block devices:"
echo ""

lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,LABEL,UUID | grep -v "loop"

echo ""
echo "========================================="
echo ""
echo "To identify your drives:"
echo "1. Look for devices with TYPE='part' (partitions)"
echo "2. Match them by SIZE and LABEL to your drives"
echo "3. Copy the UUID values"
echo ""
echo "Alternative command to see only USB devices:"
echo "  lsblk -o NAME,SIZE,LABEL,UUID | grep -A2 usb"
echo ""
echo "Or use blkid (requires sudo):"
echo "  sudo blkid -o list"
echo ""
