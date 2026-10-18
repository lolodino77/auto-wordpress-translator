"""Vérifie les brouillons créés (lecture seule) : statut, titre, tags, mots, notes. Usage : python check_drafts.py ID [ID ...] [--grep MOT]"""
import json
import re
import sys
import tomllib

import requests
import truststore

truststore.inject_into_ssl()
args = sys.argv[1:]
grep = args[args.index("--grep") + 1] if "--grep" in args else None
ctx = int(args[args.index("--ctx") + 1]) if "--ctx" in args else 80
ids = [a for a in args if a.isdigit()]
site = tomllib.loads(open("config.toml", encoding="utf-8").read())["wordpress"]["site"]
token = json.load(open("wp_token.json", encoding="utf-8"))["access_token"]
for pid in ids:
    r = requests.get(f"https://public-api.wordpress.com/rest/v1.1/sites/{site}/posts/{pid}",
                     headers={"Authorization": f"Bearer {token}"}, timeout=30)
    r.raise_for_status()
    p = r.json()
    text = re.sub(r"<[^>]+>", " ", p["content"])
    print(f"{pid} | {p['status']} | {len(text.split())} mots | {p['title']} | tags: {list(p['tags'])}")
    print("    fin:", re.sub(r"\s+", " ", text)[-110:])
    notes = re.findall(r"\[\[.*?\]\]", p["content"], re.S)
    print(f"    notes [[ ]] : {len(notes)} | '[[' : {p['content'].count('[[')} | ']]' : {p['content'].count(']]')}")
    for n in notes:
        print("      -", re.sub(r"\s+", " ", n)[:170])
    if grep:
        for m in re.finditer(grep, p["content"], re.I):
            print(f"    [{grep}] ...{re.sub(chr(10), ' ', p['content'][max(0, m.start()-ctx):m.end()+ctx])}...")
