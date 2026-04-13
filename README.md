# Newsletter ? PDF

A small Python tool that scrapes page images from Publitas-hosted flipbook newsletters and merges them into a single PDF. Browser automation uses [Playwright](https://playwright.dev/python/); images are handled with [Pillow](https://python-pillow.org/); PDF output uses [ReportLab](https://www.reportlab.com/).

## Requirements

- Python 3.8+ (recommended)
- Chromium (installed via Playwright setup)

## Setup

```bash
pip install playwright Pillow reportlab
python -m playwright install chromium
```

## Usage

```bash
python getBulten.py
```

Edit the settings at the top of `getBulten.py` to match your newsletter before running.

## Configuration (top of `getBulten.py`)

| Variable | Description |
|----------|-------------|
| `BASE_URL` | The Publitas page URL base ending with `page/` (e.g. `.../issue-name/.../page/`). |
| `TOTAL_PAGES` | Total page count (odd pages are grouped as spreads). |
| `OUTPUT_PDF` | Output PDF filename. |
| `QUALITY_CANDIDATES` | Image quality suffixes to try (`at2x`, `at1200`, …); the highest available is chosen. |
| `DELAY_MS` | Wait after load (ms); increase if images load slowly. |

## How it works

1. Spread URLs are built (Publitas often shows two pages at once: `1`, `2-3`, `4-5`, …).
2. Each URL is opened in Chromium; image URLs on `view.publitas.com` are collected from network/HTML.
3. The best available quality tag is detected from the first image; all URLs are upgraded to that quality.
4. Images are downloaded in order and written to one PDF.

## Troubleshooting

- **No images found:** Increase `DELAY_MS` and retry; the site layout or your connection may have changed.
- **404 / lower quality:** If a high quality is missing, the script falls back to something like `at600`.
- **Wrong page count:** `TOTAL_PAGES` and `BASE_URL` must match the real publication structure.

## License

If no license file is included with the project, terms are up to the project owner.
