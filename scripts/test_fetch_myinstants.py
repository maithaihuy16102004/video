import os
import re
import sys
import time
import json
import urllib.request
import urllib.parse
from pathlib import Path

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'vi,en-US;q=0.9,en;q=0.8,fr;q=0.7',
}

url = 'https://www.myinstants.com/fr/index/vn/'
req = urllib.request.Request(url, headers=headers)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode('utf-8', errors='replace')
        print(f"Fetched {url} - Status {resp.status} - Length: {len(html)}")
        with open("myinstants_sample.html", "w", encoding="utf-8") as f:
            f.write(html)
except Exception as e:
    print(f"Error fetching {url}: {e}")
