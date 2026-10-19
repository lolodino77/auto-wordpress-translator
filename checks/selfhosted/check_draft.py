"""Lecture seule : relit un brouillon d'un site auto-hébergé. Usage : python checks/selfhosted/check_draft.py ID"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # dossier du projet
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import html
import tomllib

import requests

import wp_selfhosted as ws

site = tomllib.loads(Path("config.toml").read_text(encoding="utf-8"))["wordpress"]["site"]
r = requests.get(ws._api(site, f"posts/{sys.argv[1]}"), params={"context": "edit"}, auth=ws._auth(), timeout=30)
print(f"HTTP {r.status_code}")
if r.status_code != 200:
    print(r.text[:600])
    sys.exit(2)
p = r.json()
content = p["content"].get("raw") or p["content"]["rendered"]
text = html.unescape(re.sub(r"<[^>]+>", " ", content))
notes = re.findall(r"\[\[.*?\]\]", content, re.S)
print(f"n° {p['id']} | statut : {p['status']} | auteur n° {p['author']}")
print(f"titre : {html.unescape(p['title'].get('raw') or p['title']['rendered'])}")
print(f"slug (identifiant) : {p['slug']!r} | catégories : {p.get('categories')} | étiquettes : {p.get('tags')}")
print(f"{len(text.split())} mots | titres h3 : {len(re.findall('<h3', content))}, h4 : {len(re.findall('<h4', content))} | "
      f"notes [[ ]] : {len(notes)} ('[[' {content.count('[[')} / ']]' {content.count(']]')}) | se termine par <hr> : "
      f"{content.rstrip().endswith('<hr>')}")
print(f"début : {re.sub(chr(10), ' ', content[:260])}")
for n in notes:
    print("  note :", re.sub(r"\s+", " ", html.unescape(n))[:170])
print(f"fin : ...{re.sub(chr(10), ' ', content[-200:])}")
