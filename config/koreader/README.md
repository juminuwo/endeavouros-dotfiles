# KOReader configuration

KOReader mixes portable preferences with device-specific and frequently
changing state in `settings.reader.lua`. Symlinking that file would dirty the
dotfiles repository during normal reading and could copy Android paths, device
IDs, or desktop window geometry between machines.

- `settings.reader.lua` is a sanitized first-run template. The installer copies
  it only when `~/.config/koreader/settings.reader.lua` does not already exist.
- `defaults.custom.lua` is stable and symlinked for advanced overrides.
- The live settings directory remains local and writable.

Do not commit `settings/kosync.lua`, `settings/opds.lua`, cloud credentials,
histories, reading-statistics databases, caches, downloaded plugins, fonts,
dictionaries, sidecars, or recent-document state. These belong to the live
KOReader directory and the existing machine backup workflow.
