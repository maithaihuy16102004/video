"""Myinstants Vietnam Meme Scraper & Cloner.
Downloads top Vietnam meme sounds from https://www.myinstants.com/fr/index/vn/
Saves to d:\\Agent\\assets\\memes and creates an indexed catalog.json.
"""
import os
import re
import sys
import json
import time
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import unicodedata

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TARGET_DIR = Path(r"d:\Agent\assets\memes")
TARGET_DIR.mkdir(parents=True, exist_ok=True)

# Also ensure symlink or alias folder d:\Agent\memes
ALIAS_DIR = Path(r"d:\Agent\memes")
ALIAS_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'vi,en-US;q=0.9,en;q=0.8',
}

def slugify(text: str) -> str:
    # remove accents
    nfkd_form = unicodedata.normalize('NFKD', text)
    only_ascii = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    clean = re.sub(r'[^a-zA-Z0-9_-]+', '_', only_ascii).strip('_').lower()
    return clean[:45] if clean else "meme"

def fetch_page(page_num: int):
    url = f"https://www.myinstants.com/fr/index/vn/?page={page_num}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode('utf-8', errors='replace')
            # Extract items: sound_url, page_link, title
            matches = re.findall(
                r"play\('([^']+\.mp3)'[^>]*>.*?<a href=\"([^\"]+)\" class=\"instant-link[^\"]*\">([^<]+)</a>",
                html, re.DOTALL
            )
            items = []
            for sound_url, page_link, raw_title in matches:
                title = raw_title.strip()
                if not sound_url.startswith("http"):
                    full_sound_url = f"https://www.myinstants.com{sound_url}"
                else:
                    full_sound_url = sound_url
                items.append({
                    "title": title,
                    "sound_url": full_sound_url,
                    "page_link": f"https://www.myinstants.com{page_link}",
                    "page": page_num
                })
            return items
    except Exception as e:
        print(f"Error fetching page {page_num}: {e}")
        return []

def download_sound(item: dict) -> dict:
    title = item["title"]
    sound_url = item["sound_url"]
    slug = slugify(title)
    
    # Extract original filename
    orig_name = sound_url.split('/')[-1]
    filename = f"{slug}.mp3"
    filepath = TARGET_DIR / filename
    
    # If collision, append short hash
    if filepath.exists() and filepath.stat().st_size > 0:
        item["local_path"] = str(filepath)
        item["filename"] = filename
        item["status"] = "CACHED"
        item["size"] = filepath.stat().st_size
        return item

    req = urllib.request.Request(sound_url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            if len(data) > 0:
                with open(filepath, "wb") as f:
                    f.write(data)
                # also write or copy to alias
                alias_path = ALIAS_DIR / filename
                try:
                    with open(alias_path, "wb") as f2:
                        f2.write(data)
                except Exception:
                    pass
                item["local_path"] = str(filepath)
                item["filename"] = filename
                item["status"] = "DOWNLOADED"
                item["size"] = len(data)
                return item
    except Exception as e:
        item["status"] = f"FAILED: {e}"
        item["size"] = 0
        return item
    item["status"] = "EMPTY"
    item["size"] = 0
    return item

def main():
    print("=== Myinstants Vietnam Meme Scraper & Cloner ===")
    print(f"Target folder: {TARGET_DIR}")
    print(f"Alias folder:  {ALIAS_DIR}")
    
    # We will fetch first 6 pages (36 * 6 = 216 memes)
    total_pages = 6
    all_items = []
    seen_urls = set()
    
    for p in range(1, total_pages + 1):
        print(f"Scraping page {p}/{total_pages}...")
        page_items = fetch_page(p)
        for it in page_items:
            if it["sound_url"] not in seen_urls:
                seen_urls.add(it["sound_url"])
                all_items.append(it)
        time.sleep(0.5)
        
    print(f"\nDiscovered {len(all_items)} unique meme sounds. Starting concurrent download...")
    
    successful = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(download_sound, item): item for item in all_items}
        for fut in as_completed(futures):
            res = fut.result()
            if res.get("size", 0) > 0:
                successful.append(res)
                if len(successful) % 25 == 0 or len(successful) == len(all_items):
                    print(f"  Downloaded {len(successful)}/{len(all_items)} memes...")
                    
    print(f"\nSuccessfully stored {len(successful)} meme audio files into {TARGET_DIR}!")
    
    # Build catalog
    catalog = {
        "version": "1.0",
        "source": "https://www.myinstants.com/fr/index/vn/",
        "total_memes": len(successful),
        "target_dir": str(TARGET_DIR),
        "alias_dir": str(ALIAS_DIR),
        "memes": []
    }
    
    for idx, item in enumerate(successful):
        catalog["memes"].append({
            "id": f"meme_{idx+1:03d}",
            "title": item["title"],
            "filename": item["filename"],
            "slug": slugify(item["title"]),
            "sound_url": item["sound_url"],
            "page_link": item["page_link"],
            "size_bytes": item["size"],
            "local_path": item["local_path"]
        })
        
    catalog_path = TARGET_DIR / "catalog.json"
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
        
    # Also write into alias dir
    with open(ALIAS_DIR / "catalog.json", "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
        
    print(f"Catalog created: {catalog_path}")
    print(f"Sample memes:")
    for m in catalog["memes"][:10]:
        print(f" - [{m['id']}] {m['title']} -> {m['filename']} ({m['size_bytes']} bytes)")

if __name__ == "__main__":
    main()
