from __future__ import annotations

import importlib.util
import struct
import sys
import tempfile
import unittest
import zipfile
import zlib
from importlib.machinery import SourceFileLoader
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "bin"
    / "repair-japanese-epubs"
)
LOADER = SourceFileLoader("repair_japanese_epubs", str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
REPAIR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REPAIR
LOADER.exec_module(REPAIR)


def make_epub(
    path: Path,
    *,
    root_attributes: str = "",
    body_class: str = "vbody",
    css: str = ".vbody { writing-mode: vertical-rl; }\n",
    second_root_attributes: str | None = None,
    second_body_class: str = "hbody",
) -> object:
    container = """<?xml version="1.0" encoding="UTF-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"
           version="1.0">
  <rootfiles>
    <rootfile full-path="content.opf"
              media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
    second_manifest = """
    <item id="chapter2" href="chapter2.xhtml"
          media-type="application/xhtml+xml"/>""" if second_root_attributes is not None else ""
    second_spine = (
        '\n    <itemref idref="chapter2"/>'
        if second_root_attributes is not None
        else ""
    )
    package = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf"
         xmlns:dc="http://purl.org/dc/elements/1.1/"
         version="3.0" unique-identifier="id">
  <metadata>
    <dc:identifier id="id">fixture</dc:identifier>
    <dc:title>Japanese root-mode fixture</dc:title>
    <dc:language>ja</dc:language>
    <meta property="dcterms:modified">2026-08-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="chapter" href="chapter.xhtml"
          media-type="application/xhtml+xml"/>{second_manifest}
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"
          properties="nav"/>
    <item id="style" href="style.css" media-type="text/css"/>
  </manifest>
  <spine page-progression-direction="rtl">
    <itemref idref="chapter"/>{second_spine}
  </spine>
</package>
"""
    navigation = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops">
  <head><title>Contents</title></head>
  <body>
    <nav epub:type="toc">
      <ol><li><a href="chapter.xhtml">Fixture</a></li></ol>
    </nav>
  </body>
</html>
"""
    second_chapter = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"{second_root_attributes or ""}>
  <head>
    <title>Fixture 2</title>
    <link rel="stylesheet" type="text/css" href="style.css"/>
  </head>
  <body class="{second_body_class}"><p>横書き</p></body>
</html>
"""
    chapter = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"{root_attributes}>
  <head>
    <title>Fixture</title>
    <link rel="stylesheet" type="text/css" href="style.css"/>
  </head>
  <body class="{body_class}">
    <p id="paragraph"><a href="#paragraph">縦書き</a></p>
  </body>
</html>
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "mimetype",
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("content.opf", package)
        archive.writestr("nav.xhtml", navigation)
        archive.writestr("chapter.xhtml", chapter)
        if second_root_attributes is not None:
            archive.writestr("chapter2.xhtml", second_chapter)
        archive.writestr("style.css", css)
    return REPAIR.Book(
        book_id=1,
        title="fixture",
        relative_dir="fixture",
        format_name="fixture",
        database_languages=("jpn",),
        path=path,
    )


def add_central_only_mimetype_extra(path: Path) -> bytes:
    """Add an Info-ZIP Unicode path field only to mimetype's central entry."""
    filename = b"mimetype"
    payload = struct.pack("<BI", 1, zlib.crc32(filename)) + filename
    extra = struct.pack("<HH", 0x7075, len(payload)) + payload
    data = bytearray(path.read_bytes())
    eocd_offset = data.rfind(b"PK\x05\x06")
    if eocd_offset < 0:
        raise AssertionError("fixture ZIP has no end-of-central-directory record")
    central_size = struct.unpack_from("<I", data, eocd_offset + 12)[0]
    central_offset = struct.unpack_from("<I", data, eocd_offset + 16)[0]
    if data[central_offset : central_offset + 4] != b"PK\x01\x02":
        raise AssertionError("fixture ZIP central directory is malformed")
    filename_length = struct.unpack_from("<H", data, central_offset + 28)[0]
    extra_length = struct.unpack_from("<H", data, central_offset + 30)[0]
    if data[
        central_offset + 46 : central_offset + 46 + filename_length
    ] != filename:
        raise AssertionError("mimetype is not the fixture's first central entry")
    if extra_length:
        raise AssertionError("fixture mimetype already has a central extra field")
    insert_at = central_offset + 46 + filename_length
    data[insert_at:insert_at] = extra
    struct.pack_into("<H", data, central_offset + 30, len(extra))
    struct.pack_into("<I", data, eocd_offset + len(extra) + 12, central_size + len(extra))
    path.write_bytes(data)
    return extra


def local_extra_length(path: Path, member: str) -> int:
    with zipfile.ZipFile(path) as archive:
        offset = archive.getinfo(member).header_offset
    return struct.unpack_from("<H", path.read_bytes(), offset + 28)[0]


class JapaneseEpubRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(
            prefix="test-repair-japanese-epubs-"
        )
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_rewrite_strips_central_only_mimetype_extra(self) -> None:
        book = make_epub(self.temp_path / "central-extra.epub")
        source_extra = add_central_only_mimetype_extra(book.path)

        self.assertEqual(local_extra_length(book.path, "mimetype"), 0)
        with zipfile.ZipFile(book.path) as archive:
            self.assertEqual(archive.getinfo("mimetype").extra, source_extra)

        patched = self.temp_path / "central-extra-patched.epub"
        REPAIR.write_patched_epub(book.path, patched, {})

        self.assertEqual(local_extra_length(patched, "mimetype"), 0)
        with zipfile.ZipFile(patched) as archive:
            mimetype = archive.getinfo("mimetype")
            self.assertEqual(mimetype.extra, b"")
            self.assertEqual(mimetype.compress_type, zipfile.ZIP_STORED)
            self.assertEqual(archive.read(mimetype), b"application/epub+zip")
        REPAIR.validate_epub(patched)

    def test_body_only_vertical_mode_gets_principal_root_repair(self) -> None:
        book = make_epub(self.temp_path / "body-only.epub")

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "needs-fix")
        self.assertEqual(
            audit.root_class_updates,
            ("chapter.xhtml=vrtl",),
        )
        patched = self.temp_path / "patched.epub"
        REPAIR.write_patched_epub(
            book.path,
            patched,
            audit.member_updates,
        )
        repaired_book = REPAIR.Book(
            book_id=book.book_id,
            title=book.title,
            relative_dir=book.relative_dir,
            format_name=book.format_name,
            database_languages=book.database_languages,
            path=patched,
        )
        self.assertEqual(REPAIR.audit_book(repaired_book).status, "ok")

    def test_root_class_only_repair_uses_existing_principal_css(self) -> None:
        book = make_epub(
            self.temp_path / "class-only.epub",
            root_attributes=' dir="ltr"',
            css=(
                ".vbody { writing-mode: vertical-rl; }\n"
                "html.vrtl { writing-mode: vertical-rl; }\n"
            ),
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "needs-fix")
        self.assertEqual(audit.root_class_updates, ("chapter.xhtml=vrtl",))
        self.assertEqual(audit.missing_modes, ())
        self.assertEqual(audit.root_direction_updates, ())
        self.assertIsNone(audit.css_member)
        self.assertEqual(set(audit.member_updates), {"chapter.xhtml"})
        patched = self.temp_path / "class-only-patched.epub"
        REPAIR.write_patched_epub(book.path, patched, audit.member_updates)
        repaired_book = REPAIR.Book(
            book_id=book.book_id,
            title=book.title,
            relative_dir=book.relative_dir,
            format_name=book.format_name,
            database_languages=book.database_languages,
            path=patched,
        )
        self.assertEqual(REPAIR.audit_book(repaired_book).status, "ok")

    def test_inline_horizontal_root_conflict_is_rejected(self) -> None:
        book = make_epub(
            self.temp_path / "inline-conflict.epub",
            root_attributes=' style="writing-mode: horizontal-tb"',
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "unsupported")

    def test_body_selector_does_not_satisfy_principal_root_mode(self) -> None:
        book = make_epub(
            self.temp_path / "body-selector.epub",
            root_attributes=' class="vrtl"',
            body_class="vrtl",
            css=(
                "body.vrtl { writing-mode: vertical-rl; }\n"
            ),
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "needs-fix")
        self.assertEqual(audit.missing_modes, ("vrtl",))

    def test_conflicting_principal_css_modes_are_rejected(self) -> None:
        book = make_epub(
            self.temp_path / "css-conflict.epub",
            root_attributes=' class="vrtl"',
            body_class="vrtl",
            css=(
                "html.vrtl { writing-mode: vertical-rl; }\n"
                ".vrtl { writing-mode: horizontal-tb; }\n"
            ),
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "unsupported")
        self.assertIn("conflicting horizontal mode", audit.reason)

    def test_important_generic_html_mode_conflict_is_rejected(self) -> None:
        book = make_epub(
            self.temp_path / "important-html-conflict.epub",
            root_attributes=' class="vrtl"',
            body_class="vrtl",
            css=(
                "html { writing-mode: horizontal-tb !important; }\n"
                "html.vrtl { writing-mode: vertical-rl; }\n"
            ),
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "unsupported")
        self.assertIn("conflicting horizontal mode", audit.reason)

    def test_important_root_pseudo_mode_conflict_is_rejected(self) -> None:
        book = make_epub(
            self.temp_path / "important-root-conflict.epub",
            root_attributes=' class="vrtl"',
            body_class="vrtl",
            css=(
                ":root { writing-mode: horizontal-tb !important; }\n"
                "html.vrtl { writing-mode: vertical-rl; }\n"
            ),
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "unsupported")
        self.assertIn("conflicting horizontal mode", audit.reason)

    def test_descendant_body_direction_conflict_is_rejected(self) -> None:
        book = make_epub(
            self.temp_path / "descendant-direction-conflict.epub",
            root_attributes=' class="vrtl"',
            body_class="vrtl",
            css=(
                "html.vrtl { writing-mode: vertical-rl; }\n"
                "html.vrtl body { direction: rtl; }\n"
            ),
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "unsupported")
        self.assertIn("publisher-authored CSS direction", audit.reason)

    def test_body_direction_does_not_satisfy_principal_direction(self) -> None:
        css = "body.vrtl { direction: ltr; }"

        self.assertTrue(REPAIR.class_has_direction(css, "vrtl", "ltr"))
        self.assertFalse(
            REPAIR.class_has_direction(
                css,
                "vrtl",
                "ltr",
                principal=True,
            )
        )

    def test_missing_direction_is_added_to_xhtml_root_not_css(self) -> None:
        book = make_epub(
            self.temp_path / "root-direction.epub",
            root_attributes=' class="vrtl"',
            css="html.vrtl { writing-mode: vertical-rl; }\n",
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "needs-fix")
        self.assertEqual(audit.root_direction_updates, ("chapter.xhtml",))
        patched = self.temp_path / "root-direction-patched.epub"
        REPAIR.write_patched_epub(book.path, patched, audit.member_updates)
        with zipfile.ZipFile(patched) as archive:
            chapter = archive.read("chapter.xhtml").decode("utf-8")
            css = archive.read("style.css").decode("utf-8")
        self.assertIn('<html xmlns="http://www.w3.org/1999/xhtml" class="vrtl" dir="ltr">', chapter)
        self.assertNotIn("direction:", css)

    def test_existing_root_direction_is_idempotent(self) -> None:
        book = make_epub(
            self.temp_path / "already-correct.epub",
            root_attributes=" class='vrtl' dir='ltr'",
            css="html.vrtl { writing-mode: vertical-rl; }\n",
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "ok")
        self.assertEqual(audit.member_updates, {})

    def test_root_rtl_direction_is_rejected(self) -> None:
        book = make_epub(
            self.temp_path / "root-rtl.epub",
            root_attributes=' class="vrtl" dir="rtl"',
            css="html.vrtl { writing-mode: vertical-rl; }\n",
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "unsupported")
        self.assertIn("conflicting RTL", audit.reason)

    def test_legacy_generated_css_is_migrated(self) -> None:
        book = make_epub(
            self.temp_path / "legacy.epub",
            root_attributes=' class="vrtl"',
            css=(
                "html.vrtl { writing-mode: vertical-rl; }\n\n"
                f"/* {REPAIR.DIRECTION_MARKER} */\n"
                "html.vrtl {\n"
                "  direction: ltr;\n"
                "}\n"
            ),
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "needs-fix")
        self.assertEqual(audit.root_direction_updates, ("chapter.xhtml",))
        self.assertEqual(audit.removed_legacy_direction_css, ("style.css",))
        patched = self.temp_path / "legacy-patched.epub"
        REPAIR.write_patched_epub(book.path, patched, audit.member_updates)
        with zipfile.ZipFile(patched) as archive:
            self.assertNotIn(
                REPAIR.DIRECTION_MARKER,
                archive.read("style.css").decode("utf-8"),
            )
        repaired_book = REPAIR.Book(
            book_id=book.book_id,
            title=book.title,
            relative_dir=book.relative_dir,
            format_name=book.format_name,
            database_languages=book.database_languages,
            path=patched,
        )
        self.assertEqual(REPAIR.audit_book(repaired_book).status, "ok")

    def test_older_legacy_class_selector_is_migrated(self) -> None:
        book = make_epub(
            self.temp_path / "older-legacy.epub",
            root_attributes=' class="vrtl"',
            css=(
                "html.vrtl { writing-mode: vertical-rl; }\n\n"
                f"/* {REPAIR.DIRECTION_MARKER} */\n"
                ".tate-0w-off {\n"
                "  direction: ltr;\n"
                "}\n"
            ),
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "needs-fix")
        self.assertEqual(audit.removed_legacy_direction_css, ("style.css",))

    def test_unmarked_publisher_direction_is_preserved_for_manual_review(self) -> None:
        css = (
            "html.vrtl { writing-mode: vertical-rl; direction: ltr; }\n"
            ".publisher-rule { color: red; }\n"
        )
        book = make_epub(
            self.temp_path / "publisher-direction.epub",
            root_attributes=' class="vrtl"',
            css=css,
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "unsupported")
        self.assertIn("publisher-authored CSS direction", audit.reason)
        with zipfile.ZipFile(book.path) as archive:
            self.assertEqual(archive.read("style.css").decode("utf-8"), css)

    def test_root_attribute_update_preserves_existing_quote_style(self) -> None:
        source = (
            b"<?xml version='1.0'?>\n"
            b"<html xmlns='http://www.w3.org/1999/xhtml' class='vrtl' xml:lang='ja'>"
            b"<head/><body/></html>"
        )

        updated = REPAIR.update_root_attributes(source, direction="ltr")

        self.assertIn(
            b"<html xmlns='http://www.w3.org/1999/xhtml' class='vrtl' "
            b"xml:lang='ja' dir=\"ltr\">",
            updated,
        )

    def test_mixed_layout_only_adds_direction_to_vertical_document(self) -> None:
        book = make_epub(
            self.temp_path / "mixed.epub",
            root_attributes=' class="vrtl"',
            body_class="vbody",
            second_root_attributes=' class="hltr"',
            second_body_class="hbody",
            css=(
                ".vbody, html.vrtl { writing-mode: vertical-rl; }\n"
                ".hbody, html.hltr { writing-mode: horizontal-tb; }\n"
            ),
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "needs-fix")
        self.assertEqual(audit.root_direction_updates, ("chapter.xhtml",))
        self.assertEqual(set(audit.member_updates), {"chapter.xhtml"})
        patched = self.temp_path / "mixed-patched.epub"
        REPAIR.write_patched_epub(book.path, patched, audit.member_updates)
        with zipfile.ZipFile(patched) as archive:
            vertical = archive.read("chapter.xhtml").decode("utf-8")
            horizontal = archive.read("chapter2.xhtml").decode("utf-8")
        self.assertIn('dir="ltr"', vertical)
        self.assertNotIn('dir="ltr"', horizontal)

    def test_all_vertical_documents_receive_root_direction(self) -> None:
        book = make_epub(
            self.temp_path / "two-vertical.epub",
            root_attributes=' class="vrtl"',
            body_class="vbody",
            second_root_attributes=' class="vrtl"',
            second_body_class="vbody",
            css=".vbody, html.vrtl { writing-mode: vertical-rl; }\n",
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(
            audit.root_direction_updates,
            ("chapter.xhtml", "chapter2.xhtml"),
        )

    def test_hybrid_root_and_body_vertical_documents_are_all_repaired(self) -> None:
        book = make_epub(
            self.temp_path / "hybrid-vertical.epub",
            root_attributes=' class="vrtl"',
            body_class="vbody",
            second_root_attributes="",
            second_body_class="vbody",
            css=".vbody, html.vrtl { writing-mode: vertical-rl; }\n",
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "needs-fix")
        self.assertEqual(
            audit.root_direction_updates,
            ("chapter.xhtml", "chapter2.xhtml"),
        )
        self.assertEqual(
            audit.root_class_updates,
            ("chapter2.xhtml=vrtl",),
        )
        patched = self.temp_path / "hybrid-vertical-patched.epub"
        REPAIR.write_patched_epub(book.path, patched, audit.member_updates)
        repaired_book = REPAIR.Book(
            book_id=book.book_id,
            title=book.title,
            relative_dir=book.relative_dir,
            format_name=book.format_name,
            database_languages=book.database_languages,
            path=patched,
        )
        self.assertEqual(REPAIR.audit_book(repaired_book).status, "ok")

    def test_hybrid_horizontal_document_gets_principal_root_mode(self) -> None:
        book = make_epub(
            self.temp_path / "hybrid-horizontal.epub",
            root_attributes=' class="vrtl"',
            body_class="vbody",
            second_root_attributes="",
            second_body_class="hbody",
            css=(
                ".vbody, html.vrtl { writing-mode: vertical-rl; }\n"
                ".hbody, html.hltr { writing-mode: horizontal-tb; }\n"
            ),
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "needs-fix")
        self.assertEqual(audit.root_direction_updates, ("chapter.xhtml",))
        self.assertEqual(
            audit.root_class_updates,
            ("chapter2.xhtml=hltr",),
        )
        patched = self.temp_path / "hybrid-horizontal-patched.epub"
        REPAIR.write_patched_epub(book.path, patched, audit.member_updates)
        repaired_book = REPAIR.Book(
            book_id=book.book_id,
            title=book.title,
            relative_dir=book.relative_dir,
            format_name=book.format_name,
            database_languages=book.database_languages,
            path=patched,
        )
        self.assertEqual(REPAIR.audit_book(repaired_book).status, "ok")


if __name__ == "__main__":
    unittest.main()
