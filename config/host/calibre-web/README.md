# Calibre-Web

Native Calibre is the authoritative manager for the novels library. Calibre-Web
provides LAN browsing, downloads, browser reading, and OPDS using that library's
`metadata.db`.

- Calibre library: `/mnt/Main/ebooks/calibre-library`
- Raw ebook archive: `/mnt/Main/ebooks/archive`
- Raw novels: `/mnt/Main/ebooks/archive/novels`
- Raw manga/comics: `/mnt/Main/ebooks/archive/manga`
- Calibre-Web state: `~/services/calibre-web/config`
- Web UI: `http://localhost:8083`
- LAN URL: `http://<host-lan-address>:8083`
- OPDS: `http://<host-lan-address>:8083/opds`

The raw ebook archive is not mounted by this stack. Calibre-Web sees only the
Calibre-managed library. Import novels, manga, or comics into native Calibre
deliberately; Calibre copies them into its own Author/Title structure while the
source archive remains unchanged.

## Install

The live Compose path is a symlink to the repo-managed file:

```text
mkdir -p ~/services/calibre-web/config
ln -s ~/git/endeavouros-dotfiles/config/host/calibre-web/compose.yaml ~/services/calibre-web/compose.yaml
```

Do not start Calibre-Web until
`/mnt/Main/ebooks/calibre-library/metadata.db` exists.
Calibre owns the complete contents and Author/Title layout of its library.

Add books to the managed library through native Calibre. Calibre copies imports
from `/mnt/Main/ebooks/archive` or other source locations into its managed
Author/Title structure; source files remain separate unless removed manually.

## First Calibre-Web run

1. Confirm `/mnt/Main/ebooks/calibre-library/metadata.db` exists.
2. Start the stack with `docker compose up -d`.
3. Browse to `http://localhost:8083`.
4. Set **Location of Calibre database** to `/books` and save. Calibre-Web looks
   for `/books/metadata.db`; select the directory, not the database filename.
5. Log in with the initial username `admin` and password `admin123`, then change
   the password immediately.

## Lifecycle

Run these commands from `~/services/calibre-web`:

```text
docker compose stop
docker compose start
docker compose logs -f
docker compose pull
docker compose up -d
```

## Japanese EPUB writing mode

Some Japanese EPUBs declare vertical reading in their package metadata but omit
standards-based CSS needed by every reader. Missing `writing-mode: vertical-rl`
can render prose horizontally. Missing `direction: ltr` can make the logical
start of a vertical Japanese line appear at the bottom when a reader inherits
RTL from the publication's page progression.

Calibre-Web's bundled epub.js determines its pagination axis from the XHTML
`html` root. A book that applies `vertical-rl` only to `body` can look vertical
but expose only the beginning of a long chapter before **Next** jumps to the
next spine item. The repair tool therefore audits the root and body separately.
When the existing body classes classify every content document unambiguously,
it adds `vrtl` or `hltr` to the corresponding XHTML root and supplies explicit
`html.vrtl` / `html.hltr` rules in the shared stylesheet.

Audit the managed library without changing it:

```text
repair-japanese-epubs
```

To repair unambiguous compatibility gaps, first close native Calibre and stop
Calibre-Web:

```text
cd ~/services/calibre-web
docker compose stop
repair-japanese-epubs --fix
docker compose start
```

The repair is deliberately narrow. It changes root class attributes and adds
rules only where the EPUB's Japanese language, vertical package/spine intent,
effective XHTML classes, and shared stylesheet agree. Vertical lines remain
`vertical-rl`, their inline direction is made explicitly top-to-bottom with
`direction: ltr`, and the OPF page progression remains RTL. Documents already
classified as horizontal remain `horizontal-tb`. Chapter bodies, text, IDs,
links, OPF spine, navigation files, publisher layout, book names, and the raw
archive are not rewritten. Books that cannot be classified safely are reported
for manual review. Conflicting root/body inline styles, generic root rules,
descendant body direction rules, and contradictory CSS cascade candidates are
rejected rather than guessed.

Before replacing a managed EPUB through Calibre's database interface, the tool
makes a byte-for-byte backup and JSON manifest under:

```text
~/services/calibre-web/backups/japanese-epubs/<timestamp>/
```

Calibre's desktop viewer may later update its embedded reading-position data
inside an EPUB. A resulting live-file hash difference from the manifest's
`patched_sha256` does not mean the CSS repair was lost; audit the book again to
verify its effective writing mode.

Run the audit again after importing new Japanese EPUBs. A clean audit exits
successfully; an audit that finds repairable or manual-review items exits
nonzero. This standards repair cannot correct every Calibre-Web reader layout
difference because its browser reader and Calibre's desktop reader use different
rendering engines.

Run the tracked body-only, selector-applicability, inline-conflict, and cascade
regression fixtures after changing the repair tool:

```text
cd ~/git/endeavouros-dotfiles
python -m unittest -v tests.test_repair_japanese_epubs
```
