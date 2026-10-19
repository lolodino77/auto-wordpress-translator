"""Lecture seule : pour chaque article visible avec le jeton de l'application, affiche l'auteur et le droit de
modification que WordPress indique (champ capabilities). Ne modifie rien. Usage : python checks/wpcom/check_edit_scope.py"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # dossier du projet
sys.path.insert(0, str(ROOT))  # pour importer wp.py / wp_selfhosted.py
os.chdir(ROOT)  # config.toml, wp_token.json, wp_credentials.json sont lus depuis la racine du projet

import json
import tomllib

import requests
import truststore

truststore.inject_into_ssl()
site = tomllib.loads(open("config.toml", encoding="utf-8").read())["wordpress"]["site"]
headers = {"Authorization": "Bearer " + json.load(open("wp_token.json", encoding="utf-8"))["access_token"]}
r = requests.get(f"https://public-api.wordpress.com/rest/v1.1/sites/{site}/posts", headers=headers,
                 params={"number": 100, "status": "publish,pending,draft,private", "type": "post"}, timeout=30)
print(f"HTTP {r.status_code} {r.reason}")
r.raise_for_status()
posts = r.json().get("posts", [])
me = {p["author"]["login"] for p in posts if p["status"] in ("draft", "pending")}  # auteur(s) de mes brouillons
print(f"{len(posts)} article(s) visible(s). Compte(s) auteur(s) de brouillons ou d'articles en attente : {sorted(me)}\n")
print(f"{'ID':>5} | {'statut':8} | {'auteur':24} | modifier | supprimer | publier | titre")
for p in posts:
    c = p.get("capabilities", {})
    print(f"{p['ID']:>5} | {p['status']:8} | {p['author']['login'][:24]:24} | {str(c.get('edit_post')):8} | "
          f"{str(c.get('delete_post')):9} | {str(c.get('publish_post')):7} | {p['title'][:50]}")
others = [p for p in posts if p["author"]["login"] not in me]
print(f"\nArticles d'AUTRES auteurs visibles : {len(others)}")
for p in others:
    print(f"  n° {p['ID']} ({p['status']}, auteur {p['author']['login']}) : modifier={p['capabilities'].get('edit_post')}")
