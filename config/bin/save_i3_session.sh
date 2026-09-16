#!/usr/bin/env bash
# Compatibility entry point; desktop-session owns locking, feedback and recovery.
exec "$HOME/.local/bin/desktop-session" save "$@"
