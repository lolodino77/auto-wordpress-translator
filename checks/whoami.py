"""Lecture seule : à quel compte appartient l'accès de l'application, et avec quels droits ? Usage : python checks/whoami.py

Mode « selfhosted » : interroge /wp-json/wp/v2/users/me (compte, rôle, capacités). Mode « wpcom » : /me puis l'auteur des
brouillons visibles. Rien n'est créé ni modifié."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # dossier du projet
sys.path.insert(0, str(ROOT))  # pour importer wp.py / wp_selfhosted.py
os.chdir(ROOT)  # config.toml, wp_token.json, wp_credentials.json sont lus depuis la racine du projet

import json
import sys
import tomllib

import requests
import truststore

truststore.inject_into_ssl()
cfg = tomllib.loads(open("config.toml", encoding="utf-8").read())["wordpress"]
site = cfg["site"]
mode = cfg.get("mode", "wpcom")
print(f"Mode : {mode} | site (config.toml) : {site}")

if mode == "selfhosted":
    import wp_selfhosted

    cred = json.load(open(wp_selfhosted.CRED_FILE, encoding="utf-8"))
    print(f"Identifiants enregistrés pour : {cred['site']} | utilisateur : {cred['username']}\n")
    r = wp_selfhosted.me(site)
    print(f"GET /wp-json/wp/v2/users/me?context=edit -> HTTP {r.status_code} {r.reason}")
    if r.status_code != 200:
        print("--- corps brut ---")
        print(r.text[:1500])
        sys.exit(2)
    me = r.json()
    caps = me.get("capabilities", {})
    print(f"Compte : identifiant « {me.get('slug')} » | nom affiché « {me.get('name')} » | n° {me.get('id')}")
    print(f"Rôle(s) : {me.get('roles')}\n")
    print("Droits pertinents (True = le compte peut) :")
    for cap, meaning in [
        ("edit_posts", "créer/modifier ses articles"),
        ("publish_posts", "PUBLIER des articles"),
        ("edit_published_posts", "modifier ses articles déjà publiés"),
        ("delete_posts", "supprimer ses articles non publiés"),
        ("delete_published_posts", "supprimer ses articles publiés"),
        ("edit_others_posts", "modifier les articles des AUTRES"),
        ("delete_others_posts", "supprimer les articles des AUTRES"),
        ("upload_files", "envoyer des fichiers"),
        ("manage_categories", "créer/gérer catégories et étiquettes"),
        ("edit_pages", "modifier les pages"),
        ("manage_options", "changer les réglages du site"),
        ("install_plugins", "installer des plugins"),
        ("list_users", "lister les utilisateurs"),
    ]:
        print(f"  {str(bool(caps.get(cap))):5} {cap:24} {meaning}")
    sys.exit(0)

# --- mode wpcom (OAuth) ---
token = json.load(open("wp_token.json", encoding="utf-8"))
headers = {"Authorization": "Bearer " + token["access_token"]}
root = "https://public-api.wordpress.com/rest/v1.1"
print(f"Site du jeton (wp_token.json) : {token.get('blog_url') or token.get('blog_id') or '(non indiqué)'}")
print(f"Droits demandés (config.toml) : {cfg.get('scope') or '(défaut)'}\n")
r = requests.get(f"{root}/me", headers=headers, timeout=30)
print(f"1. /me : HTTP {r.status_code} {r.reason}\n{r.text[:800]}")
r2 = requests.get(f"{root}/sites/{site}/posts", headers=headers, timeout=30,
                  params={"number": 20, "status": "draft,pending", "type": "post"})
print(f"2. Auteurs des brouillons visibles : HTTP {r2.status_code}")
if r2.status_code == 200:
    print("   ", sorted({p["author"]["login"] for p in r2.json().get("posts", [])}) or "(aucun)")
else:
    print(r2.text[:400])
