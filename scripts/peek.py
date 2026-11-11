import re

with open("myinstants_sample.html", "r", encoding="utf-8") as f:
    html = f.read()

idx = html.find("play(")
print(html[idx:idx+600])
