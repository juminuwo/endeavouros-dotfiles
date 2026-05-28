#!/usr/bin/env python3
"""Helpers for Imoto Labs one-pager screenshot, crop, render, and validation work."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


SECRET_PATTERN = re.compile(
    r"£|\$[0-9]|BOM|SKU|password|secret|token|api key|api_key|credential",
    re.IGNORECASE,
)


def find_command(candidates: list[str]) -> str | None:
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return path
    return None


def chrome_command() -> str | None:
    return find_command(
        ["google-chrome-stable", "google-chrome", "chromium", "chromium-browser"]
    )


def require_command(name: str, candidates: list[str] | None = None) -> str:
    cmd = find_command(candidates or [name])
    if not cmd:
        names = ", ".join(candidates or [name])
        raise SystemExit(f"missing required command: {names}")
    return cmd


def run(cmd: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def source_to_url(source: str) -> str:
    if source.startswith(("http://", "https://", "file://")):
        return source
    source_path = Path(source).expanduser()
    if not source_path.exists():
        raise SystemExit(f"input does not exist and is not a URL: {source}")
    return source_path.resolve().as_uri()


def check_deps(_: argparse.Namespace) -> int:
    deps = {
        "chrome": chrome_command(),
        "magick": find_command(["magick"]),
        "pdfinfo": find_command(["pdfinfo"]),
        "pdftotext": find_command(["pdftotext"]),
        "pdftoppm": find_command(["pdftoppm"]),
    }
    missing = [name for name, path in deps.items() if not path]
    for name, path in deps.items():
        print(f"{name}: {path or 'MISSING'}")
    if missing:
        print(f"missing dependencies: {', '.join(missing)}", file=sys.stderr)
        return 1
    return 0


def screenshot(args: argparse.Namespace) -> int:
    chrome = require_command("chrome", ["google-chrome-stable", "google-chrome", "chromium", "chromium-browser"])
    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        f"--window-size={args.width},{args.height}",
        f"--force-device-scale-factor={args.scale}",
        f"--virtual-time-budget={args.wait_ms}",
        f"--screenshot={output}",
        source_to_url(args.input),
    ]
    run(cmd)
    print(output)
    return 0


def crop(args: argparse.Namespace) -> int:
    magick = require_command("magick")
    input_path = Path(args.input).expanduser()
    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    run([magick, str(input_path), "-crop", args.geometry, "+repage", str(output)])
    print(output)
    return 0


def render(args: argparse.Namespace) -> int:
    chrome = require_command("chrome", ["google-chrome-stable", "google-chrome", "chromium", "chromium-browser"])
    html = Path(args.html).expanduser().resolve()
    if not html.exists():
        raise SystemExit(f"HTML file does not exist: {html}")
    out_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else html.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.name or html.stem
    preview = out_dir / f"{stem}-preview.png"
    pdf = out_dir / f"{stem}.pdf"
    url = html.as_uri()

    run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            f"--window-size={args.width},{args.height}",
            f"--force-device-scale-factor={args.scale}",
            f"--virtual-time-budget={args.wait_ms}",
            f"--screenshot={preview}",
            url,
        ]
    )
    run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf}",
            url,
        ]
    )
    print(preview)
    print(pdf)
    return 0


def pdfinfo_text(pdf: Path) -> str:
    return run(["pdfinfo", str(pdf)], capture=True).stdout


def validate(args: argparse.Namespace) -> int:
    require_command("pdfinfo")
    require_command("pdftotext")
    failed = False
    pattern = re.compile(args.scan_pattern, re.IGNORECASE) if args.scan_pattern else SECRET_PATTERN

    for pdf_arg in args.pdfs:
        pdf = Path(pdf_arg).expanduser()
        if not pdf.exists():
            print(f"{pdf}: missing", file=sys.stderr)
            failed = True
            continue

        info = pdfinfo_text(pdf)
        pages_match = re.search(r"^Pages:\s+(\d+)$", info, re.MULTILINE)
        size_match = re.search(r"^Page size:\s+(.+)$", info, re.MULTILINE)
        rot_match = re.search(r"^Page rot:\s+(\d+)$", info, re.MULTILINE)
        pages = int(pages_match.group(1)) if pages_match else None
        size = size_match.group(1) if size_match else ""
        rotation = int(rot_match.group(1)) if rot_match else None

        text = run(["pdftotext", str(pdf), "-"], capture=True).stdout
        matches = [m.group(0) for m in pattern.finditer(text)]

        ok = pages == 1 and "A4" in size and rotation == 0 and not matches
        status = "OK" if ok else "FAIL"
        print(f"{status}: {pdf}")
        print(f"  pages={pages} size={size or 'unknown'} rotation={rotation}")
        if matches:
            print(f"  scan matches: {', '.join(sorted(set(matches)))}")
        if not ok:
            failed = True

    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check-deps", help="Verify render tool dependencies")
    check.set_defaults(func=check_deps)

    shot = subparsers.add_parser("screenshot", help="Capture a URL or HTML file to PNG")
    shot.add_argument("input", help="URL, file:// URL, or local HTML file")
    shot.add_argument("output", help="Output PNG path")
    shot.add_argument("--width", type=int, default=1400)
    shot.add_argument("--height", type=int, default=900)
    shot.add_argument("--scale", type=float, default=1.0)
    shot.add_argument("--wait-ms", type=int, default=5000)
    shot.set_defaults(func=screenshot)

    cropper = subparsers.add_parser("crop", help="Crop an image using ImageMagick geometry")
    cropper.add_argument("input", help="Input image")
    cropper.add_argument("output", help="Output image")
    cropper.add_argument("geometry", help="ImageMagick crop geometry, e.g. 920x1000+0+240")
    cropper.set_defaults(func=crop)

    renderer = subparsers.add_parser("render", help="Render HTML to preview PNG and PDF")
    renderer.add_argument("html", help="HTML file to render")
    renderer.add_argument("--output-dir", help="Output directory; defaults to the HTML directory")
    renderer.add_argument("--name", help="Output stem; defaults to the HTML filename stem")
    renderer.add_argument("--width", type=int, default=794)
    renderer.add_argument("--height", type=int, default=1123)
    renderer.add_argument("--scale", type=float, default=2.0)
    renderer.add_argument("--wait-ms", type=int, default=1000)
    renderer.set_defaults(func=render)

    validator = subparsers.add_parser("validate", help="Validate one-page A4 PDFs and scan text")
    validator.add_argument("pdfs", nargs="+", help="PDF file(s)")
    validator.add_argument("--scan-pattern", help="Override the default pricing/secrets scan regex")
    validator.set_defaults(func=validate)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            print(exc.stdout, file=sys.stdout)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        return exc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
