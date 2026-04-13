"""
Publitas Flipbook → PDF downloader (Playwright / JS render)
==========================================================
Setup:
    pip install playwright Pillow reportlab
    python -m playwright install chromium

Usage:
    python getBulten.py
"""

import re
import os
from io import BytesIO
from PIL import Image
from reportlab.pdfgen import canvas
from playwright.sync_api import sync_playwright

# ─── SETTINGS ─────────────────────────────────────────────────────────────────
BASE_URL    = "https://view.publitas.com/statu-co/{your-url-here}/page/"
TOTAL_PAGES = 32
OUTPUT_PDF  = "your-output-file-name.pdf"

# Quality candidates to try (highest first). On first image, all are tested; highest available wins.
QUALITY_CANDIDATES = ["at2x", "at1200", "at800", "at600", "at400"]

DELAY_MS = 2000
# ──────────────────────────────────────────────────────────────────────────────


def detect_best_quality(sample_url, pw_page):
    """
    Takes a known image URL, swaps the quality suffix, and returns the highest
    quality that responds successfully.
    """
    print("\n🔍 Testing available quality options...")
    # Find current suffix (at400 / at600 / at800, etc.)
    current = re.search(r'at\d+x?', sample_url)
    if not current:
        print("  Could not detect suffix; defaulting to 'at600'.")
        return "at600"

    current_tag = current.group(0)
    base = sample_url[:current.start()]
    ext  = sample_url[current.end():]   # usually ".jpg"

    for quality in QUALITY_CANDIDATES:
        test_url = base + quality + ext
        try:
            resp = pw_page.request.get(test_url, timeout=10000)
            if resp.ok:
                size_kb = len(resp.body()) // 1024
                print(f"  ✓ {quality} OK ({size_kb} KB)")
                print(f"  → Highest quality: {quality}")
                return quality
            else:
                print(f"  ✗ {quality} → HTTP {resp.status}")
        except Exception as e:
            print(f"  ✗ {quality} → {e}")

    print(f"  None worked; keeping '{current_tag}'.")
    return current_tag


def build_page_urls(total):
    urls = [BASE_URL + "1"]
    page = 2
    while page <= total:
        if page + 1 <= total:
            urls.append(BASE_URL + f"{page}-{page+1}")
            page += 2
        else:
            urls.append(BASE_URL + str(page))
            page += 1
    return urls


def extract_image_urls_playwright(page_url, pw_page, quality_tag):
    collected = []

    def on_request(request):
        url = request.url
        # Capture any known quality tag (we upgrade later)
        if re.search(r'at\d+x?\.jpg', url) and url not in collected:
            collected.append(url)

    pw_page.on("request", on_request)

    try:
        pw_page.goto(page_url, wait_until="networkidle", timeout=30000)
    except Exception:
        try:
            pw_page.goto(page_url, wait_until="domcontentloaded", timeout=20000)
            pw_page.wait_for_timeout(DELAY_MS)
        except Exception as e:
            print(f"  [!] Page failed to load: {e}")
            pw_page.remove_listener("request", on_request)
            return []

    pw_page.wait_for_timeout(DELAY_MS)

    html = pw_page.content()
    pattern = re.compile(
        r'https://view\.publitas\.com/\d+/\d+/pages/[a-f0-9]+-at\d+x?\.jpg'
    )
    for match in pattern.finditer(html):
        url = match.group(0)
        if url not in collected:
            collected.append(url)

    pw_page.remove_listener("request", on_request)

    # Bump all URLs to the chosen quality tag
    upgraded = []
    for url in collected:
        new_url = re.sub(r'at\d+x?(?=\.jpg)', quality_tag, url)
        if new_url not in upgraded:
            upgraded.append(new_url)

    return upgraded


def download_image(url, pw_page):
    try:
        response = pw_page.request.get(url, timeout=20000)
        if response.ok:
            return Image.open(BytesIO(response.body())).convert("RGB")
        else:
            # If high quality is missing, try a lower tier
            fallback = re.sub(r'at\d+x?(?=\.jpg)', 'at600', url)
            if fallback != url:
                print(f"  [~] {url.split('/')[-1]} not found, trying at600...")
                resp2 = pw_page.request.get(fallback, timeout=20000)
                if resp2.ok:
                    return Image.open(BytesIO(resp2.body())).convert("RGB")
            print(f"  [!] HTTP {response.status}: {url}")
            return None
    except Exception as e:
        print(f"  [!] Image download failed: {url} -> {e}")
        return None


def images_to_pdf(images, output_path):
    if not images:
        print("[!] No images; PDF not created.")
        return

    c = canvas.Canvas(output_path)
    for i, img in enumerate(images):
        w_px, h_px = img.size
        w_pt = w_px * 72 / 96
        h_pt = h_px * 72 / 96
        c.setPageSize((w_pt, h_pt))
        tmp = f"_tmp_page_{i:04d}.jpg"
        img.save(tmp, format="JPEG", quality=95)
        c.drawImage(tmp, 0, 0, width=w_pt, height=h_pt)
        c.showPage()
        os.remove(tmp)
        print(f"  ✓ Added to PDF: {i+1}/{len(images)}")

    c.save()
    print(f"\n✅ PDF saved: {output_path}")


def main():
    page_urls = build_page_urls(TOTAL_PAGES)
    print(f"📄 Built {len(page_urls)} spread URL(s).\n")

    all_image_urls = []
    best_quality   = None   # Set when the first real image is found

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        pw_page = context.new_page()

        for i, purl in enumerate(page_urls):
            print(f"[{i+1}/{len(page_urls)}] Scanning: {purl}")

            # Scan with at600 first for detection; resolve best quality from first URL
            img_urls_raw = extract_image_urls_playwright(purl, pw_page, "at600")

            if img_urls_raw and best_quality is None:
                # Run quality probe on the first image found
                best_quality = detect_best_quality(img_urls_raw[0], pw_page)

            # If we detected a quality, rewrite URLs
            if best_quality and best_quality != "at600":
                img_urls = [re.sub(r'at\d+x?(?=\.jpg)', best_quality, u) for u in img_urls_raw]
            else:
                img_urls = img_urls_raw

            if img_urls:
                print(f"  -> Found {len(img_urls)} image URL(s).")
                all_image_urls.extend(img_urls)
            else:
                print("  -> No images found.")

        # Deduplicate
        seen = set()
        unique_urls = []
        for u in all_image_urls:
            if u not in seen:
                seen.add(u)
                unique_urls.append(u)

        print(f"\n🖼  Total unique images: {len(unique_urls)}")
        print(f"📐 Quality in use: {best_quality or 'at600'}\n")

        if not unique_urls:
            print("⚠️  No images found. Try increasing DELAY_MS and run again.")
            browser.close()
            return

        print("📥 Downloading images...\n")
        images = []
        for j, url in enumerate(unique_urls):
            print(f"  [{j+1}/{len(unique_urls)}] {url.split('/')[-1]}")
            img = download_image(url, pw_page)
            if img:
                images.append(img)

        browser.close()

    print(f"\n📑 Building PDF ({len(images)} page(s))...")
    images_to_pdf(images, OUTPUT_PDF)


if __name__ == "__main__":
    main()
