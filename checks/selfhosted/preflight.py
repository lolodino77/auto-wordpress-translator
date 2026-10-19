"""Vérification AVANT une exécution sur un site auto-hébergé (lecture seule, ne crée rien).
Usage : python checks/selfhosted/preflight.py

Contrôle : identifiants, rôle, catégories lisibles, étiquettes déjà existantes du site (celles que le compte pourra poser),
et ce que contient input/articles.csv (nombre d'URLs, étiquettes demandées)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # dossier du projet
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import tomllib

import requests

import wp_selfhosted as ws
from extract import read_csv

cfg = tomllib.loads(Path("config.toml").read_text(encoding="utf-8"))
site = cfg["wordpress"]["site"]
print(f"Mode : {cfg['wordpress'].get('mode')} | site : {site}")

me = ws.me(site)
print(f"1. Compte : HTTP {me.status_code}", end=" ")
if me.status_code != 200:
    print("-> identifiants inutilisables :", me.text[:300])
    sys.exit(2)
m = me.json()
print(f"« {m['slug']} » rôle(s) {m['roles']} | publish_posts={bool(m['capabilities'].get('publish_posts'))}")

try:
    cats = ws.list_categories(site)
    print(f"2. Catégories lisibles ({len(cats)}) : {cats[:15]}{' …' if len(cats) > 15 else ''}")
except Exception as e:
    print(f"2. Catégories NON lisibles : {str(e)[:350]}")
    print("   => aucune catégorie ne sera posée automatiquement (à choisir à la main).")

tags = []
page = 1
while True:
    r = requests.get(ws._api(site, "tags"), params={"per_page": 100, "page": page}, auth=ws._auth(), timeout=30)
    if r.status_code != 200:
        print(f"   (lecture des étiquettes : HTTP {r.status_code} {r.text[:200]})")
        break
    batch = r.json()
    tags += [t["name"] for t in batch]
    if len(batch) < 100:
        break
    page += 1
print(f"3. Étiquettes existantes sur le site ({len(tags)}) : {tags[:25]}{' …' if len(tags) > 25 else ''}")
print("   (le compte NE PEUT PAS en créer : seules ces étiquettes pourront être posées)")

rows = read_csv("input/articles.csv")
print(f"4. input/articles.csv : {len(rows)} URL(s)")
for i, (url, t) in enumerate(rows, 1):
    print(f"   [{i}] {url}  étiquettes demandées : {t or '-'}")
