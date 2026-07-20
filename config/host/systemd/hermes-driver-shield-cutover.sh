#!/usr/bin/env bash

# Failure-safe migration from the retired Driver Shield Slack gateway to the
# channel-neutral gateway. This file is sourced by host-install so the cutover
# can be exercised independently with a mocked systemctl in tests.

_hermes_driver_shield_unit_state() {
  systemctl --user is-active "$1" 2>/dev/null || true
}

_hermes_driver_shield_state_is_running() {
  case "$1" in
    active|activating|reloading|deactivating) return 0 ;;
    *) return 1 ;;
  esac
}

_hermes_driver_shield_restore_old() {
  local user_unit_dir="$1"
  local old_unit="$2"
  local new_unit="$3"
  local unit_backup="$4"
  local new_state

  systemctl --user disable --now "$new_unit" >/dev/null 2>&1 || true
  new_state="$(_hermes_driver_shield_unit_state "$new_unit")"
  if _hermes_driver_shield_state_is_running "$new_state"; then
    printf 'ERROR: replacement Hermes gateway is still %s; refusing to start the old gateway.\n' \
      "$new_state" >&2
    return 1
  fi

  install -m 600 "$unit_backup" "$user_unit_dir/$old_unit"
  systemctl --user daemon-reload
  if ! systemctl --user enable --now "$old_unit"; then
    printf 'ERROR: replacement failed and the old Hermes gateway could not be restored.\n' >&2
    return 1
  fi

  if [[ "$(_hermes_driver_shield_unit_state "$old_unit")" != active ]]; then
    printf 'ERROR: restored old Hermes gateway did not become active.\n' >&2
    return 1
  fi

  printf 'Restored %s after replacement startup failed.\n' "$old_unit" >&2
}

hermes_driver_shield_cutover() {
  local user_unit_dir="$1"
  local old_unit=hermes-gateway-driver-shield-slack.service
  local new_unit=hermes-gateway-driver-shield.service
  local profile_dir="${HERMES_DRIVER_SHIELD_PROFILE_DIR:-$HOME/.hermes/profiles/driver-shield}"
  local backup_dir="${HERMES_DRIVER_SHIELD_CUTOVER_BACKUP_DIR:-$HOME/.local/state/driver-shield/hermes-service-cutover}"
  local unit_backup="$backup_dir/$old_unit"
  local old_state
  local new_state
  local old_was_running=0

  for required in \
    "$profile_dir/config.yaml" \
    "$profile_dir/.env" \
    "$profile_dir/auth.json" \
    "$profile_dir/plugins/driver-shield/plugin.yaml"; do
    if [[ ! -r "$required" ]]; then
      printf 'ERROR: replacement Hermes profile preflight failed; missing %s\n' "$required" >&2
      return 1
    fi
  done

  if ! systemctl --user cat "$new_unit" >/dev/null 2>&1; then
    printf 'ERROR: replacement Hermes unit is not loadable: %s\n' "$new_unit" >&2
    return 1
  fi

  old_state="$(_hermes_driver_shield_unit_state "$old_unit")"
  if _hermes_driver_shield_state_is_running "$old_state"; then
    old_was_running=1
    if [[ ! -r "$user_unit_dir/$old_unit" ]]; then
      printf 'ERROR: active old Hermes unit cannot be backed up from %s\n' \
        "$user_unit_dir/$old_unit" >&2
      return 1
    fi
    mkdir -p "$backup_dir"
    chmod 700 "$backup_dir"
    install -m 600 "$user_unit_dir/$old_unit" "$unit_backup"

    # Stop may fail when a unit is already disappearing. Its observed state is
    # authoritative: never remove it or start the replacement while it runs.
    systemctl --user disable --now "$old_unit" >/dev/null 2>&1 || true
    old_state="$(_hermes_driver_shield_unit_state "$old_unit")"
    if _hermes_driver_shield_state_is_running "$old_state"; then
      printf 'ERROR: old Hermes gateway remains %s; aborting cutover.\n' "$old_state" >&2
      return 1
    fi
  else
    systemctl --user disable "$old_unit" >/dev/null 2>&1 || true
  fi

  rm -f \
    "$user_unit_dir/default.target.wants/$new_unit"
  systemctl --user daemon-reload

  if ! systemctl --user enable --now "$new_unit"; then
    if ((old_was_running)); then
      _hermes_driver_shield_restore_old \
        "$user_unit_dir" "$old_unit" "$new_unit" "$unit_backup" || true
    fi
    return 1
  fi

  new_state="$(_hermes_driver_shield_unit_state "$new_unit")"
  if [[ "$new_state" != active ]]; then
    printf 'ERROR: replacement Hermes gateway entered %s during cutover.\n' "$new_state" >&2
    if ((old_was_running)); then
      _hermes_driver_shield_restore_old \
        "$user_unit_dir" "$old_unit" "$new_unit" "$unit_backup" || true
    fi
    return 1
  fi

  # Remove the retired unit only after the replacement is confirmed active.
  rm -f \
    "$user_unit_dir/$old_unit" \
    "$user_unit_dir/default.target.wants/$old_unit" \
    "$user_unit_dir/work.target.wants/$old_unit"
  systemctl --user daemon-reload
}
