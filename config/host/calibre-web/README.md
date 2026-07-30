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
can render prose horizontally. The top-to-bottom inline direction belongs on
each vertical XHTML root as `dir="ltr"`; CSS `direction` is prohibited by the
EPUB specification and can make Google Play Books reject the publication.

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
Calibre-Web. The tracked `epubcheck` package is required because every staged
EPUB must pass EPUBCheck before the library is changed:

```text
cd ~/services/calibre-web
docker compose stop
repair-japanese-epubs --fix
docker compose start
```

Limit a repair to one or more Calibre IDs when testing a new import:

```text
repair-japanese-epubs --book-id 68 --fix
```

The repair is deliberately narrow. It changes root class attributes and adds
rules only where the EPUB's Japanese language, vertical package/spine intent,
effective XHTML classes, and shared stylesheet agree. Vertical lines remain
`vertical-rl`, their XHTML root receives `dir="ltr"`, and the OPF page
progression remains RTL. Documents already classified as horizontal remain
`horizontal-tb`. The tool migrates only the obsolete CSS `direction` block
identified by its own legacy marker; publisher-authored `direction` declarations
are preserved and reported for manual review. Chapter bodies, text, IDs, links,
OPF spine, publisher layout, book names, and the raw archive are not otherwise
rewritten. Books that cannot be classified safely are reported rather than
guessed.

Some converted Japanese books declare EPUB 2 while using EPUB 3 features such
as `ruby` and right-to-left page progression. EPUBCheck will reject them even
after the direction repair. Stage a minimal package upgrade, validate it, and
only then replace the Calibre format:

```text
ebook-polish --upgrade-book input.epub upgraded.epub
epubcheck upgraded.epub
```

The staged upgrade still needs the same writing-mode audit and must be installed
through `calibredb add_format` deliberately; `repair-japanese-epubs` never
upgrades a package automatically. Do not use `ebook-convert` for this
compatibility fix because it rewrites book content and layout much more broadly.
Preserve the original in the backup directory and confirm spine order,
normalized text, and image hashes before replacement.

Before replacing a managed EPUB through Calibre's database interface, the tool
makes a byte-for-byte backup and JSON manifest under:

```text
/mnt/Main/ebooks/archive/backups/japanese-epubs/<timestamp>/
```

Calibre's desktop viewer may later update its embedded reading-position data
inside an EPUB. A resulting live-file hash difference from the manifest's
`patched_sha256` does not mean the CSS repair was lost; audit the book again to
verify its effective writing mode.

Each manifest records the XHTML files given `dir="ltr"`, any root writing-mode
classes/rules added, the legacy generated CSS blocks removed, and EPUBCheck
success. The repair also rechecks the source hash immediately before Calibre
replaces the format so a concurrently changed EPUB is never overwritten.

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
