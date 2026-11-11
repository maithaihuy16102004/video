import re
import json

with open("myinstants_sample.html", "r", encoding="utf-8") as f:
    html = f.read()

# Let's inspect how buttons and sound links are structured
instants = []

# Pattern 1: <div class="instant"> ...
instant_blocks = re.findall(r'<div class="instant[^"]*"[^>]*>(.*?)</div>\s*</div>', html, re.DOTALL)
print(f"Instant blocks found: {len(instant_blocks)}")

# Let's search for play('...') or data-sound or mp3 links
play_matches = re.findall(r"play\(['\"]([^'\"]+)['\"]", html)
print(f"play() calls found: {len(play_matches)}")
if play_matches:
    print("Sample play paths:", play_matches[:5])

# Search for instant-link
links = re.findall(r'<a[^>]*class="instant-link[^"]*"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', html)
print(f"instant-link found: {len(links)}")
if links:
    print("Sample links:", links[:5])

# Search for pagination
pages = re.findall(r'href="(/fr/index/vn/\?page=\d+)"', html)
print("Pagination links:", set(pages))
