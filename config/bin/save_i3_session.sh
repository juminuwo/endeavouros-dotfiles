#!/bin/bash

# Define the workspaces you want to save.
# Workspaces 6 and 7 are reserved for project-switch and must not be saved
# by i3-resurrect — see restore_i3_session.sh for the full reasoning.
WORKSPACES="10 9 8 5 4 3 2 1"
PROFILE_NAME="windows_switch_session" # Use a descriptive profile name

echo "Starting i3-resurrect save process..."

for ws in $WORKSPACES; do
  echo "Saving workspace: $ws"
  # The main command: save the workspace and use the specified profile
  i3-resurrect save -w "$ws" -p "${PROFILE_NAME}_${ws}"
done

echo "i3 session saved successfully to profile: $PROFILE_NAME"
