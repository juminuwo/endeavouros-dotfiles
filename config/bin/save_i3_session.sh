#!/bin/bash

# Define the workspaces you want to save
WORKSPACES="10 9 8 7 6 5 4 3 2 1"
PROFILE_NAME="windows_switch_session" # Use a descriptive profile name

echo "Starting i3-resurrect save process..."

for ws in $WORKSPACES; do
  echo "Saving workspace: $ws"
  # The main command: save the workspace and use the specified profile
  i3-resurrect save -w "$ws" -p "${PROFILE_NAME}_${ws}"
done

echo "i3 session saved successfully to profile: $PROFILE_NAME"
