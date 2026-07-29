from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import zipfile
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
    package = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf"
         xmlns:dc="http://purl.org/dc/elements/1.1/"
         version="3.0" unique-identifier="id">
  <metadata>
    <dc:identifier id="id">fixture</dc:identifier>
    <dc:title>Japanese root-mode fixture</dc:title>
    <dc:language>ja</dc:language>
    <meta property="rendition:writing-mode">vertical-rl</meta>
  </metadata>
  <manifest>
    <item id="chapter" href="chapter.xhtml"
          media-type="application/xhtml+xml"/>
    <item id="style" href="style.css" media-type="text/css"/>
  </manifest>
  <spine page-progression-direction="rtl">
    <itemref idref="chapter"/>
  </spine>
</package>
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
        archive.writestr("chapter.xhtml", chapter)
        archive.writestr("style.css", css)
    return REPAIR.Book(
        book_id=1,
        title="fixture",
        relative_dir="fixture",
        format_name="fixture",
        database_languages=("jpn",),
        path=path,
    )


class JapaneseEpubRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(
            prefix="test-repair-japanese-epubs-"
        )
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

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
            css=(
                ".vbody { writing-mode: vertical-rl; }\n"
                "html.vrtl { writing-mode: vertical-rl; direction: ltr; }\n"
            ),
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "needs-fix")
        self.assertEqual(audit.root_class_updates, ("chapter.xhtml=vrtl",))
        self.assertEqual(audit.missing_modes, ())
        self.assertEqual(audit.missing_direction_selectors, ())
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
                "html.vrtl { direction: ltr; }\n"
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
                "html.vrtl { writing-mode: vertical-rl; direction: ltr; }\n"
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
                "html.vrtl { writing-mode: vertical-rl; direction: ltr; }\n"
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
                "html.vrtl { writing-mode: vertical-rl; direction: ltr; }\n"
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
                "html.vrtl { writing-mode: vertical-rl; direction: ltr; }\n"
                "html.vrtl body { direction: rtl; }\n"
            ),
        )

        audit = REPAIR.audit_book(book)

        self.assertEqual(audit.status, "unsupported")
        self.assertIn("conflicting RTL", audit.reason)

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


if __name__ == "__main__":
    unittest.main()
