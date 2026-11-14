"""Export the M5 Markdown to PDF with locally supplied Times New Roman fonts."""

import argparse
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--font-dir", required=True, type=Path, help="Directory containing times*.ttf"
    )
    args = parser.parse_args()
    regular = (args.font_dir / "times.ttf").resolve(strict=True)
    bold = (args.font_dir / "timesbd.ttf").resolve(strict=True)

    html = subprocess.run(
        ["pandoc", str(ROOT / "MILESTONE5.md"), "--from", "markdown", "--to", "html"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    css = f"""
@font-face {{ font-family: 'M5 Times'; src: url('{regular.as_uri()}'); font-weight: 400; }}
@font-face {{ font-family: 'M5 Times'; src: url('{bold.as_uri()}'); font-weight: 700; }}
@page {{ size: A4; margin: 25mm 22mm; }}
body {{ font-family: 'M5 Times', serif; font-size: 12pt; line-height: 1.5; color: #111; }}
p {{ margin: 0 0 14pt; }}
a {{ color: #164c9d; overflow-wrap: anywhere; }}
code {{ font-family: inherit; font-size: inherit; }}
img {{ max-width: 100%; }}
table {{ border-collapse: collapse; width: 100%; margin: 0 0 14pt; font-size: 10.5pt; line-height: 1.3; }}
th, td {{ border: 1px solid #222; padding: 4pt 6pt; text-align: left; vertical-align: top; overflow-wrap: anywhere; }}
th {{ background: #f0f0f0; }}
tr {{ break-inside: avoid; }}
thead {{ display: table-header-group; }}
"""
    with tempfile.TemporaryDirectory(prefix="marketplace-m5-") as tmp:
        path = Path(tmp) / "submission.html"
        path.write_text(
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f"<base href='{ROOT.as_uri()}/'><title>Team 01 M5</title></head><body>{html}</body></html>",
            encoding="utf-8",
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True, args=["--allow-file-access-from-files"]
            )
            try:
                page = browser.new_page()
                page.goto(path.as_uri(), wait_until="load")
                page.add_style_tag(content=css)
                page.evaluate("document.fonts.ready")
                if not page.evaluate("document.fonts.check('12pt M5 Times')"):
                    raise RuntimeError("Times New Roman did not load")
                page.pdf(
                    path=str(ROOT / "MILESTONE5.pdf"),
                    print_background=True,
                    prefer_css_page_size=True,
                )
            finally:
                browser.close()


if __name__ == "__main__":
    main()
