import re

with open("myinstants_sample.html", "r", encoding="utf-8") as f:
    html = f.read()

# Let's find all occurrences of play(...) and the nearby text or anchor
pattern = r"<button[^>]*class=\"small-button[^\"]*\"[^>]*onclick=\"play\('([^']+)'\)[^>]*>.*?</button>\s*<a[^>]*href=\"([^\"]+)\"[^>]*>([^<]+)</a>"
matches = re.findall(pattern, html, re.DOTALL)
print("Matches with pattern:", len(matches))
if matches:
    for sound_url, page_url, title in matches[:10]:
        print(f"Title: {title.strip()} | Sound: {sound_url} | Page: {page_url}")
else:
    # Let's print around play(
    idx = html.find("play(")
    print("Around play( :")
    print(html[idx-100:idx+300])
