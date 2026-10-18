"""Test : crée UN brouillon "[TEST]" sur WordPress.com à partir d'une traduction déjà faite dans output/."""
import html
import re
import tomllib

import wp

cfg = tomllib.loads(open("config.toml", encoding="utf-8").read())
page = open("output/05-christmas-is-for-kids.html", encoding="utf-8").read()
title = html.unescape(re.search(r"<h1>(.*?)</h1>", page, re.S).group(1))
tags = [t.strip() for t in re.search(r"Tags : (.*?) \|", page).group(1).split(",")]
content = page.split("</h1>", 1)[1].strip()
url = wp.create_draft(cfg["wordpress"]["site"], "[TEST] " + title, content, tags)
print("BROUILLON CREE :", url)
