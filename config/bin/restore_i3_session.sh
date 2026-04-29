#!/bin/bash

# Define the workspaces you want to restore
WORKSPACES="10 9 8 7 6 5 4 3 2 1"
PROFILE_NAME="windows_switch_session"

echo "Starting i3-resurrect restore process..."

# Step 1: Restore the LAYOUTS first to create placeholder windows
for ws in $WORKSPACES; do
  echo "Restoring layout for workspace: $ws"
  # Use --layout-only to create the layout structure and placeholder windows
  i3-resurrect restore -w "$ws" -p "${PROFILE_NAME}_${ws}" --layout-only
done

# Step 2: Restore the PROGRAMS, which should be swallowed by the layouts
for ws in $WORKSPACES; do
  echo "Restoring programs for workspace: $ws"
  # Use --programs-only to launch the programs
  i3-resurrect restore -w "$ws" -p "${PROFILE_NAME}_${ws}" --programs-only &
done

echo "i3 session restore commands executed."
