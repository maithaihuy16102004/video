import re

with open("myinstants_sample.html", "r", encoding="utf-8") as f:
    html = f.read()

# Let's find one instant block and print it
m = re.search(r'(<div class="instant[^"]*"[^>]*>.*?)(?=<div class="instant|\Z)', html, re.DOTALL)
if m:
    print("First instant block:")
    print(m.group(1)[:1000])

# Check pagination pattern
pagination = re.findall(r'<div class="pagination"[^>]*>(.*?)</div>', html, re.DOTALL)
if pagination:
    print("Pagination block:")
    print(pagination[0])
else:
    # search any page links
    any_pages = re.findall(r'href="[^"]*page=\d+[^"]*"', html)
    print("Any page links:", set(any_pages))
