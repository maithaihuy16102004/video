import urllib.request
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
}

for page in [1, 2, 3]:
    url = f"https://www.myinstants.com/fr/index/vn/?page={page}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='replace')
            items = re.findall(r"play\('([^']+\.mp3)'[^>]*>.*?<a href=\"([^\"]+)\" class=\"instant-link[^\"]*\">([^<]+)</a>", html, re.DOTALL)
            print(f"Page {page}: found {len(items)} items")
            if items:
                print(f"   First: {items[0][2]} -> {items[0][0]}")
    except Exception as e:
        print(f"Page {page} error: {e}")
