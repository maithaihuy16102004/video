import urllib.request
import re

headers = {'User-Agent': 'Mozilla/5.0'}
for p in range(1, 10):
    url = f"https://www.myinstants.com/fr/index/vn/?page={p}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as r:
            html = r.read().decode('utf-8', errors='replace')
            items = re.findall(r"play\('([^']+\.mp3)'[^>]*>.*?<a href=\"([^\"]+)\" class=\"instant-link[^\"]*\">([^<]+)</a>", html, re.DOTALL)
            print(f"Page {p}: {len(items)} items")
            if len(items) == 0:
                break
    except Exception as e:
        print(f"Page {p} stopped: {e}")
        break
