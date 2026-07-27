# LANraragi

LANraragi is the personal comics/manga server.

- Archives: `/mnt/Main/ebooks/manga`
- Database: `~/.local/share/lanraragi/database`
- Thumbnails: `~/.local/share/lanraragi/thumb`
- Web UI: `http://localhost:3002`

The container listens on all LAN interfaces at port `3002` so mobile clients can
reach it at `http://<host-lan-address>:3002`. Do not expose this port directly
to the public internet; use a VPN or authenticated reverse proxy for remote
access.

## Lifecycle

```text
cd ~/git/endeavouros-dotfiles/config/host/lanraragi
docker compose up -d
docker compose pull
docker compose up -d
```

The service uses Docker's `unless-stopped` restart policy, matching the
host's Jellyfin setup.

## Missing archives

Shinobu scans the archive directory when LANraragi starts, then watches it for
filesystem changes. If the directory is populated after that initial scan and
the filesystem event is missed, the library can remain empty even though the
bind mount and permissions are correct.

Use **Configuration → Files → Rescan Archive Directory** in LANraragi. This is
the supported full rescan: it resets Shinobu's internal filemap and restarts the
watcher without deleting the archive files or library metadata. Do not delete
Redis data or edit files inside the container.

After the scan finishes, verify that `/api/info` reports a nonzero
`total_archives` and `/api/search` returns HTTP 200 with a JSON response.
